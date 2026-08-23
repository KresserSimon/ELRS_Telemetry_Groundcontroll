"""One-shot IP-based geolocation lookup, used by the Home Position dialog as
a quick way to prefill lat/lon without typing them by hand. City-level
accuracy only (a few km) - good enough for picking the right map region,
not a substitute for a real GPS fix or manual entry.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Tuple

_API_URL = "https://ipapi.co/json/"
_TIMEOUT_S = 8


class IpGeolocationError(RuntimeError):
    """The IP geolocation lookup failed (no network, service down, or an
    unexpected response) - callers must not silently fall back to a
    guessed position."""


def lookup_ip_location() -> Tuple[float, float]:
    request = urllib.request.Request(_API_URL, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT_S) as response:
            body = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, OSError) as exc:
        raise IpGeolocationError(f"Standort konnte nicht ermittelt werden: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise IpGeolocationError(f"Ungültige Antwort vom Standort-Dienst: {exc}") from exc

    if body.get("error"):
        raise IpGeolocationError(str(body.get("reason") or "Standort-Dienst meldete einen Fehler."))
    try:
        return float(body["latitude"]), float(body["longitude"])
    except (KeyError, TypeError, ValueError) as exc:
        raise IpGeolocationError("Unerwartete Antwort vom Standort-Dienst.") from exc
