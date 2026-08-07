"""Minimal CRSF (Crossfire/ExpressLRS) telemetry frame parser.

Used when a bridge (e.g. an ESP32 "backpack") forwards the raw CRSF byte
stream over UDP instead of translating it to MAVLink first. Only the frame
types relevant to a ground-station dashboard are decoded; everything else is
skipped. Field layouts/offsets below come from the CRSF protocol spec and are
not self-explanatory from the code alone, hence the inline notes.
"""
from __future__ import annotations

import struct
from typing import Dict, List, Optional

CRSF_SYNC_BYTE = 0xC8
FRAMETYPE_GPS = 0x02
FRAMETYPE_BATTERY_SENSOR = 0x08
FRAMETYPE_LINK_STATISTICS = 0x14
FRAMETYPE_FLIGHT_MODE = 0x21

MAX_FRAME_LEN = 64

# ELRS TX power enum -> mW
_TX_POWER_MAP = {0: 0, 1: 10, 2: 25, 3: 100, 4: 500, 5: 1000, 6: 2000, 7: 250, 8: 50}


def crc8_dvb_s2(data: bytes) -> int:
    crc = 0
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = ((crc << 1) ^ 0xD5) & 0xFF if crc & 0x80 else (crc << 1) & 0xFF
    return crc


class CRSFParser:
    """Stateful byte-stream -> telemetry-field-dict extractor.

    Feed it raw bytes as they arrive from the socket; it returns a list of
    dicts (one per successfully decoded frame) with the fields that frame
    updates, e.g. {'lat': 48.1, 'lon': 11.5, 'alt': 120.0, 'satellites': 9}.
    """

    def __init__(self) -> None:
        self._buf = bytearray()

    def feed(self, data: bytes) -> List[Dict]:
        self._buf.extend(data)
        results: List[Dict] = []

        while True:
            frame = self._try_extract_frame()
            if frame is None:
                break
            parsed = self._parse_frame(frame)
            if parsed:
                results.append(parsed)

        return results

    def _try_extract_frame(self) -> Optional[bytes]:
        buf = self._buf
        if len(buf) < 2:
            return None

        # buf[0] = address/sync, buf[1] = length of (type + payload + crc)
        length = buf[1]
        if length < 2 or length > MAX_FRAME_LEN:
            # Not a plausible CRSF frame at this offset; resync by one byte.
            del buf[0]
            return None

        total = 2 + length
        if len(buf) < total:
            return None  # wait for more bytes

        frame = bytes(buf[:total])
        del buf[:total]

        expected_crc = frame[-1]
        actual_crc = crc8_dvb_s2(frame[2:-1])
        if actual_crc != expected_crc:
            return None  # drop silently, keep scanning subsequent frames

        return frame

    def _parse_frame(self, frame: bytes) -> Optional[Dict]:
        frame_type = frame[2]
        payload = frame[3:-1]

        try:
            if frame_type == FRAMETYPE_GPS and len(payload) == 15:
                return self._parse_gps(payload)
            if frame_type == FRAMETYPE_BATTERY_SENSOR and len(payload) == 8:
                return self._parse_battery(payload)
            if frame_type == FRAMETYPE_LINK_STATISTICS and len(payload) == 10:
                return self._parse_link_stats(payload)
            if frame_type == FRAMETYPE_FLIGHT_MODE:
                return self._parse_flight_mode(payload)
        except struct.error:
            return None

        return None

    @staticmethod
    def _parse_gps(payload: bytes) -> Dict:
        lat, lon, groundspeed, heading, altitude, satellites = struct.unpack(">iiHHHB", payload)
        return {
            "lat": lat / 1e7,
            "lon": lon / 1e7,
            "alt": altitude - 1000.0,      # CRSF encodes altitude with +1000m offset
            "heading": heading / 100.0,
            "satellites": satellites,
        }

    @staticmethod
    def _parse_battery(payload: bytes) -> Dict:
        voltage, current = struct.unpack(">HH", payload[0:4])
        remaining = payload[7]
        return {
            "battery_voltage": voltage / 10.0,
            "battery_remaining": remaining,
        }

    @staticmethod
    def _parse_link_stats(payload: bytes) -> Dict:
        (
            up_rssi_1, up_rssi_2, up_lq, up_snr,
            _active_antenna, _rf_mode, up_tx_power,
            _down_rssi, _down_lq, _down_snr,
        ) = struct.unpack(">BBBbBBBBBb", payload)

        rssi = max(up_rssi_1, up_rssi_2)
        return {
            "rssi": -rssi,
            "link_quality": up_lq,
            "snr": float(up_snr),
            "tx_power": _TX_POWER_MAP.get(up_tx_power),
        }

    @staticmethod
    def _parse_flight_mode(payload: bytes) -> Dict:
        text = payload.split(b"\x00", 1)[0].decode("ascii", errors="ignore").strip()
        return {"flight_mode": text} if text else {}
