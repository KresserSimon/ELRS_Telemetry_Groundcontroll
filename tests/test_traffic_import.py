import json
import unittest
import urllib.error
from unittest.mock import MagicMock, patch

from core.traffic_import import (
    PROVIDER_AIRPLANES_LIVE,
    PROVIDER_OPENSKY,
    TrafficFetchError,
    fetch_traffic,
)


def _response(body):
    mock = MagicMock()
    mock.read.return_value = json.dumps(body).encode("utf-8")
    mock.__enter__.return_value = mock
    mock.__exit__.return_value = False
    return mock


class FetchAirplanesLiveTest(unittest.TestCase):
    @patch("core.traffic_import.urllib.request.urlopen")
    def test_parses_known_fields_and_converts_units(self, mock_urlopen):
        mock_urlopen.return_value = _response({
            "ac": [{
                "hex": "3c6444", "flight": "DLH123 ", "lat": 48.2, "lon": 11.6,
                "alt_baro": 35000, "track": 270, "gs": 450, "baro_rate": -500,
            }]
        })
        result = fetch_traffic(PROVIDER_AIRPLANES_LIVE, "https://api.airplanes.live/v2/point", 48.1, 11.5, 30.0)
        self.assertEqual(len(result), 1)
        ac = result[0]
        self.assertEqual(ac.icao24, "3c6444")
        self.assertEqual(ac.callsign, "DLH123")
        self.assertAlmostEqual(ac.alt_m, 35000 * 0.3048)
        self.assertAlmostEqual(ac.groundspeed_ms, 450 * 0.514444)
        self.assertAlmostEqual(ac.vertical_rate_ms, -500 * 0.00508)
        self.assertEqual(ac.heading_deg, 270)

    @patch("core.traffic_import.urllib.request.urlopen")
    def test_ground_altitude_string_becomes_zero(self, mock_urlopen):
        mock_urlopen.return_value = _response({
            "ac": [{"hex": "abc123", "lat": 48.2, "lon": 11.6, "alt_baro": "ground"}]
        })
        result = fetch_traffic(PROVIDER_AIRPLANES_LIVE, "https://api.airplanes.live/v2/point", 48.1, 11.5, 30.0)
        self.assertEqual(result[0].alt_m, 0.0)

    @patch("core.traffic_import.urllib.request.urlopen")
    def test_contact_without_position_is_skipped_not_fatal(self, mock_urlopen):
        mock_urlopen.return_value = _response({
            "ac": [{"hex": "no-pos"}, {"hex": "has-pos", "lat": 1.0, "lon": 2.0}]
        })
        result = fetch_traffic(PROVIDER_AIRPLANES_LIVE, "https://api.airplanes.live/v2/point", 48.1, 11.5, 30.0)
        self.assertEqual([ac.icao24 for ac in result], ["has-pos"])

    @patch("core.traffic_import.urllib.request.urlopen")
    def test_missing_ac_key_raises(self, mock_urlopen):
        mock_urlopen.return_value = _response({"total": 0})
        with self.assertRaises(TrafficFetchError):
            fetch_traffic(PROVIDER_AIRPLANES_LIVE, "https://api.airplanes.live/v2/point", 48.1, 11.5, 30.0)

    @patch("core.traffic_import.urllib.request.urlopen")
    def test_network_failure_raises(self, mock_urlopen):
        mock_urlopen.side_effect = urllib.error.URLError("no network")
        with self.assertRaises(TrafficFetchError):
            fetch_traffic(PROVIDER_AIRPLANES_LIVE, "https://api.airplanes.live/v2/point", 48.1, 11.5, 30.0)


class FetchOpenSkyTest(unittest.TestCase):
    @patch("core.traffic_import.urllib.request.urlopen")
    def test_parses_state_vector_preferring_geo_altitude(self, mock_urlopen):
        state = ["3c6444", "DLH123  ", "Germany", 0, 0, 11.6, 48.2, 10000.0, False, 200.0, 90.0, 1.5]
        state += [None] * 5  # pad to index 16 (sensors..position_source)
        state[13] = 10600.0  # geo_altitude
        mock_urlopen.return_value = _response({"time": 0, "states": [state]})
        result = fetch_traffic(PROVIDER_OPENSKY, "https://opensky-network.org/api/states/all", 48.1, 11.5, 30.0)
        self.assertEqual(len(result), 1)
        ac = result[0]
        self.assertEqual(ac.icao24, "3c6444")
        self.assertEqual(ac.callsign, "DLH123")
        self.assertEqual(ac.alt_m, 10600.0)
        self.assertEqual(ac.groundspeed_ms, 200.0)
        self.assertEqual(ac.heading_deg, 90.0)

    @patch("core.traffic_import.urllib.request.urlopen")
    def test_no_states_returns_empty_not_error(self, mock_urlopen):
        mock_urlopen.return_value = _response({"time": 0, "states": None})
        result = fetch_traffic(PROVIDER_OPENSKY, "https://opensky-network.org/api/states/all", 48.1, 11.5, 30.0)
        self.assertEqual(result, [])

    @patch("core.traffic_import.urllib.request.urlopen")
    def test_state_without_position_is_skipped(self, mock_urlopen):
        incomplete = ["icao1", "CS1"] + [None] * 15
        mock_urlopen.return_value = _response({"time": 0, "states": [incomplete]})
        result = fetch_traffic(PROVIDER_OPENSKY, "https://opensky-network.org/api/states/all", 48.1, 11.5, 30.0)
        self.assertEqual(result, [])


if __name__ == "__main__":
    unittest.main()
