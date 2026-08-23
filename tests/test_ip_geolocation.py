import json
import unittest
import urllib.error
from unittest.mock import MagicMock, patch

from core.ip_geolocation import IpGeolocationError, lookup_ip_location


def _response(body: dict):
    mock = MagicMock()
    mock.read.return_value = json.dumps(body).encode("utf-8")
    mock.__enter__.return_value = mock
    mock.__exit__.return_value = False
    return mock


class LookupIpLocationTest(unittest.TestCase):
    @patch("core.ip_geolocation.urllib.request.urlopen")
    def test_parses_latitude_and_longitude(self, mock_urlopen):
        mock_urlopen.return_value = _response({"latitude": 47.5031, "longitude": 9.7472})
        self.assertEqual(lookup_ip_location(), (47.5031, 9.7472))

    @patch("core.ip_geolocation.urllib.request.urlopen")
    def test_service_error_flag_raises(self, mock_urlopen):
        mock_urlopen.return_value = _response({"error": True, "reason": "RateLimited"})
        with self.assertRaises(IpGeolocationError):
            lookup_ip_location()

    @patch("core.ip_geolocation.urllib.request.urlopen")
    def test_missing_fields_raise(self, mock_urlopen):
        mock_urlopen.return_value = _response({"latitude": 47.5031})
        with self.assertRaises(IpGeolocationError):
            lookup_ip_location()

    @patch("core.ip_geolocation.urllib.request.urlopen")
    def test_network_failure_raises(self, mock_urlopen):
        mock_urlopen.side_effect = urllib.error.URLError("no network")
        with self.assertRaises(IpGeolocationError):
            lookup_ip_location()


if __name__ == "__main__":
    unittest.main()
