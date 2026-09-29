"""Installs a process-wide crash logger so an unhandled exception - on the
main thread or inside a QThread's run() - always leaves a permanent,
findable trace, instead of only the transient console output the packaged
.exe's own console window loses the instant it aborts.

PyQt6 routes an unhandled Python exception raised inside any callback
invoked from C++ (a signal/slot connection, a QThread.run() override, a
QTimer timeout, ...) through sys.excepthook, and - unlike plain CPython
continuing after printing a traceback - may then abort the whole process
natively, since continuing after a Python exception mid-C++-callstack can
leave Qt's own C++ state inconsistent. That abort happens too fast for a
user to read (or even see) the console before the window closes with it -
this module makes sure the traceback survives that abort by writing it to
a plain text file under the same ~/.elrs_ground_station/ folder every
other core/*_config.py module already uses, before the previous hook (the
usual stderr traceback print) runs.
"""
from __future__ import annotations

import sys
import threading
import traceback
from datetime import datetime
from pathlib import Path

CRASH_LOG_PATH = Path.home() / ".elrs_ground_station" / "crash_log.txt"

# Keeps the file from growing forever across a long-lived install - capped
# at the most recent crashes rather than a byte count, so a single huge
# traceback is never cut off mid-entry.
MAX_ENTRIES = 20

_ENTRY_SEPARATOR = "\n" + ("=" * 78) + "\n"


def _format_entry(exc_type, exc_value, exc_tb, thread_name: str) -> str:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    tb_text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    return f"[{timestamp}] thread={thread_name}\n{tb_text}"


def _append_entry(entry: str) -> None:
    try:
        CRASH_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        existing = ""
        if CRASH_LOG_PATH.is_file():
            existing = CRASH_LOG_PATH.read_text(encoding="utf-8", errors="replace")
        entries = [e for e in existing.split(_ENTRY_SEPARATOR) if e.strip()]
        entries.append(entry)
        entries = entries[-MAX_ENTRIES:]
        CRASH_LOG_PATH.write_text(_ENTRY_SEPARATOR.join(entries) + _ENTRY_SEPARATOR, encoding="utf-8")
    except OSError:
        pass  # logging the crash must never itself become a second crash


def install_crash_logger() -> None:
    """Call once, as early as possible in main(). Wraps sys.excepthook
    (covers the main thread and any QThread's run(), which PyQt routes
    through sys.excepthook too) and threading.excepthook (covers a plain
    threading.Thread, if one is ever added) so every uncaught exception is
    appended to CRASH_LOG_PATH, then still falls through to whatever
    default handling ran before (stderr traceback print, PyQt6's own
    abort) - this only adds a permanent record, it doesn't change whether
    or how the app actually exits."""
    previous_excepthook = sys.excepthook

    def _sys_hook(exc_type, exc_value, exc_tb):
        _append_entry(_format_entry(exc_type, exc_value, exc_tb, threading.current_thread().name))
        previous_excepthook(exc_type, exc_value, exc_tb)

    sys.excepthook = _sys_hook

    previous_threading_hook = threading.excepthook

    def _threading_hook(args) -> None:
        _append_entry(_format_entry(args.exc_type, args.exc_value, args.exc_traceback, args.thread.name if args.thread else "?"))
        previous_threading_hook(args)

    threading.excepthook = _threading_hook
