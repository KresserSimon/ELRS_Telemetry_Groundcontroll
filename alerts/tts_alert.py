"""Offline text-to-speech battery warnings.

pyttsx3 engines are not safe to share across threads, so speech happens on a
dedicated QThread fed through a small queue; the engine instance is created
once inside run() and reused for every subsequent phrase.
"""
from __future__ import annotations

import queue

from PyQt6.QtCore import QThread

from core.telemetry_state import TelemetryState

LEVEL_NONE = "none"
LEVEL_LOW = "low"
LEVEL_CRITICAL = "critical"

REANNOUNCE_INTERVAL_S = 30.0


class TTSWorker(QThread):
    """Background speech engine. Call say() from any thread."""

    def __init__(self) -> None:
        super().__init__()
        self._queue: "queue.Queue[str]" = queue.Queue()
        self._running = True

    def say(self, text: str) -> None:
        self._queue.put(text)

    def stop(self) -> None:
        self._running = False
        self._queue.put("")  # unblock the queue.get()
        self.wait(3000)

    def run(self) -> None:
        try:
            import pyttsx3
            engine = pyttsx3.init()
        except Exception:
            engine = None

        while self._running:
            text = self._queue.get()
            if not text or engine is None:
                continue
            try:
                engine.say(text)
                engine.runAndWait()
            except Exception:
                pass


class BatteryAlertMonitor:
    """State machine that turns battery telemetry into TTS warnings.

    Uses percent-remaining when available, otherwise falls back to a
    per-cell voltage estimate. Hysteresis + a re-announce cooldown stop the
    alert from flapping or spamming every single telemetry packet.
    """

    def __init__(
        self,
        tts_worker: TTSWorker,
        cells: int = 4,
        low_percent: int = 25,
        critical_percent: int = 12,
        low_cell_voltage: float = 3.6,
        critical_cell_voltage: float = 3.5,
    ) -> None:
        self._tts = tts_worker
        self._cells = max(cells, 1)
        self._low_percent = low_percent
        self._critical_percent = critical_percent
        self._low_cell_voltage = low_cell_voltage
        self._critical_cell_voltage = critical_cell_voltage

        self._level = LEVEL_NONE
        self._last_announce = 0.0

    def check(self, state: TelemetryState) -> None:
        level = self._evaluate_level(state)
        now = state.timestamp

        if level == LEVEL_NONE:
            # Require a clear improvement above LOW before resetting (hysteresis).
            if self._level != LEVEL_NONE and not self._still_low(state):
                self._level = LEVEL_NONE
            return

        if level != self._level:
            self._level = level
            self._last_announce = now
            self._tts.say(self._message(level))
        elif (now - self._last_announce) >= REANNOUNCE_INTERVAL_S:
            self._last_announce = now
            self._tts.say(self._message(level))

    def _evaluate_level(self, state: TelemetryState) -> str:
        percent = state.battery_remaining
        per_cell = state.battery_voltage / self._cells if state.battery_voltage else None

        if percent is not None:
            if percent <= self._critical_percent:
                return LEVEL_CRITICAL
            if percent <= self._low_percent:
                return LEVEL_LOW
            return LEVEL_NONE

        if per_cell is not None:
            if per_cell <= self._critical_cell_voltage:
                return LEVEL_CRITICAL
            if per_cell <= self._low_cell_voltage:
                return LEVEL_LOW
            return LEVEL_NONE

        return LEVEL_NONE

    def _still_low(self, state: TelemetryState) -> bool:
        return self._evaluate_level(state) != LEVEL_NONE

    @staticmethod
    def _message(level: str) -> str:
        if level == LEVEL_CRITICAL:
            return "Warnung. Akku kritisch niedrig. Bitte sofort landen."
        return "Warnung. Akkuspannung niedrig."
