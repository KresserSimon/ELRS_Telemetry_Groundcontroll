import unittest

from core.telemetry_state import TelemetryState
from core.tracker_output import (
    TrackerOutputSender,
    _nmea_checksum,
    _nmea_lat,
    _nmea_lon,
    build_gpgga,
)


def _state(lat, lon, alt=100.0, satellites=8):
    s = TelemetryState()
    s.lat, s.lon, s.alt, s.satellites = lat, lon, alt, satellites
    return s


class NmeaLatLonTest(unittest.TestCase):
    def test_north_east(self):
        self.assertEqual(_nmea_lat(48.1173), "4807.0380,N")
        self.assertEqual(_nmea_lon(11.5167), "01131.0020,E")

    def test_south_west(self):
        self.assertTrue(_nmea_lat(-33.5).endswith(",S"))
        self.assertTrue(_nmea_lon(-70.25).endswith(",W"))

    def test_degrees_padding(self):
        # Longitude degrees are zero-padded to 3 digits, latitude to 2.
        lat = _nmea_lat(5.0)
        lon = _nmea_lon(5.0)
        self.assertTrue(lat.startswith("05"))
        self.assertTrue(lon.startswith("005"))


class NmeaChecksumTest(unittest.TestCase):
    def test_known_checksum(self):
        # Standard reference GPGGA body/checksum pair.
        body = "GPGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,"
        self.assertEqual(_nmea_checksum(body), "47")


class BuildGpggaTest(unittest.TestCase):
    def test_well_formed_sentence(self):
        sentence = build_gpgga(_state(48.1173, 11.5167))
        self.assertTrue(sentence.startswith("$GPGGA,"))
        self.assertTrue(sentence.endswith("\r\n"))
        body, _, checksum = sentence[1:-2].partition("*")
        self.assertEqual(_nmea_checksum(body), checksum)

    def test_missing_satellites_and_alt_default_to_zero(self):
        state = _state(48.0, 11.0, alt=None, satellites=None)
        sentence = build_gpgga(state)
        fields = sentence[1:].split(",")
        self.assertIn("00", fields)  # satellite count field


class TrackerOutputSenderTest(unittest.TestCase):
    def test_inactive_by_default(self):
        sender = TrackerOutputSender()
        self.assertFalse(sender.is_active())

    def test_send_without_start_is_a_noop(self):
        sender = TrackerOutputSender()
        # Must not raise even though nothing was started.
        sender.send(_state(48.0, 11.0))

    def test_send_without_gps_fix_is_a_noop(self):
        sender = TrackerOutputSender()
        sender._udp_socket = object()  # pretend "active" without opening a real socket
        state = TelemetryState()  # lat/lon None -> no fix
        sender.send(state)  # must not attempt to touch the fake socket

    def test_stop_is_safe_when_never_started(self):
        sender = TrackerOutputSender()
        sender.stop()  # must not raise
        self.assertFalse(sender.is_active())


if __name__ == "__main__":
    unittest.main()
