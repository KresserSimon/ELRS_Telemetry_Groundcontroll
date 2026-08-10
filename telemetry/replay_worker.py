"""Replays a previously recorded flight-log CSV (export/flight_logger.py)
through the exact same telemetry_received signal every live backend uses -
see docs/feature_plan.md's "Log-Replay". Every parsed sample's
TelemetryState.source is "replay", which is exactly the flag
MainWindow._on_telemetry() already checks (see the P2-prep Refactoring #1)
to skip TTS warnings, live track recording, and the external tracker-
output connection while replaying - no separate replay-aware code path
needed anywhere else in the app.

CSV timestamps are only second-resolution (see flight_logger.py's
_field_value()) - playback timing between samples is therefore only as
fine-grained as the original logging interval, not smoother than that.
"""
from __future__ import annotations

import csv
import queue
import time
from typing import List, Optional, Tuple

from PyQt6.QtCore import pyqtSignal

from core.telemetry_state import TelemetryState
from telemetry.base_worker import TelemetryWorker

_INT_FIELDS = ("satellites", "gps_fix", "battery_remaining", "rssi", "link_quality", "tx_power", "rpm")
_MAX_GAP_MS = 2000  # cap so a paused-logging gap doesn't stall playback for minutes


def _parse_value(field: str, raw: str):
    if raw == "":
        return None
    if field == "timestamp":
        return time.mktime(time.strptime(raw, "%Y-%m-%dT%H:%M:%S"))
    if field == "cell_voltages":
        return [float(v) for v in raw.split("|") if v]
    if field in _INT_FIELDS:
        return int(float(raw))
    if field == "connected":
        return raw.strip().lower() in ("true", "1")
    if field == "flight_mode":
        return raw
    try:
        return float(raw)
    except ValueError:
        return raw


def parse_flight_log_csv(path: str) -> List[TelemetryState]:
    """Tolerant of any subset/order of export/flight_logger.py's ALL_FIELDS
    columns (the logger's field selection is user-configurable) - a
    missing column just leaves that TelemetryState field at its default
    (usually None), an unknown/future column is silently ignored."""
    states: List[TelemetryState] = []
    with open(path, "r", newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        try:
            header = next(reader)
        except StopIteration:
            return states
        has_timestamp = "timestamp" in header
        for i, row in enumerate(reader):
            state = TelemetryState(source="replay", connected=True)
            for field, raw in zip(header, row):
                if field == "source" or field not in TelemetryState.__dataclass_fields__:
                    continue
                value = _parse_value(field, raw)
                if value is not None:
                    setattr(state, field, value)
            if not has_timestamp:
                # No real timestamps recorded - fall back to a synthetic,
                # monotonically increasing one so playback ordering/timing
                # still works, just without real inter-sample gaps.
                state.timestamp = float(i)
            states.append(state)
    return states


class ReplayWorker(TelemetryWorker):
    # Replay-specific progress reporting for a transport UI - not part of
    # TelemetryWorker's shared base contract, since no live backend has an
    # analogous "how far through" concept.
    progress = pyqtSignal(int, int)  # (current index, total)
    finished_replay = pyqtSignal()

    def __init__(self, states: List[TelemetryState], speed: float = 1.0) -> None:
        super().__init__()
        self._states = states
        self._speed = max(0.05, speed)
        self._paused = False
        self._seek_to: Optional[int] = None
        # Control messages queued from the GUI thread, drained on this
        # worker's own thread - same thread-safety pattern established in
        # telemetry/mavlink_worker.py's enqueue_send()/_drain_send_queue().
        self._control_queue: "queue.Queue[Tuple[str, object]]" = queue.Queue()

    def set_speed(self, speed: float) -> None:
        self._control_queue.put(("speed", max(0.05, speed)))

    def set_paused(self, paused: bool) -> None:
        self._control_queue.put(("pause", paused))

    def seek(self, index: int) -> None:
        self._control_queue.put(("seek", index))

    def _drain_control_queue(self) -> None:
        while True:
            try:
                kind, value = self._control_queue.get_nowait()
            except queue.Empty:
                return
            if kind == "speed":
                self._speed = value
            elif kind == "pause":
                self._paused = value
            elif kind == "seek":
                self._seek_to = value

    def run(self) -> None:
        if not self._states:
            self.error_occurred.emit("Log-Datei enthaelt keine Telemetriedaten.")
            return

        self.connection_changed.emit(True)
        index = 0
        total = len(self._states)

        while self._running and index < total:
            self._drain_control_queue()

            if self._seek_to is not None:
                index = max(0, min(self._seek_to, total - 1))
                self._seek_to = None

            if self._paused:
                self.msleep(100)
                continue

            state = self._states[index]
            self.telemetry_received.emit(state.copy())
            self.progress.emit(index, total)

            if index + 1 < total:
                gap_s = max(0.0, self._states[index + 1].timestamp - state.timestamp)
                sleep_ms = min(int((gap_s / self._speed) * 1000), _MAX_GAP_MS)
                remaining = sleep_ms
                while self._running and remaining > 0 and self._seek_to is None and not self._paused:
                    step = min(50, remaining)
                    self.msleep(step)
                    remaining -= step
                    self._drain_control_queue()

            index += 1

        if self._running:
            self.connection_changed.emit(False)
            self.finished_replay.emit()
