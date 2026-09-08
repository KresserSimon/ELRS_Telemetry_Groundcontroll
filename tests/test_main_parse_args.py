import unittest
from unittest import mock

from main import parse_args


def _patch_saved(settings):
    return mock.patch("core.connection_config.load_connection_settings", return_value=settings)


class ParseArgsConnectionDefaultsTest(unittest.TestCase):
    def test_defaults_to_elrs_and_usb_when_nothing_saved(self):
        with _patch_saved({}):
            args = parse_args(["--demo"])
        self.assertEqual(args.protocol, "crsf")
        self.assertEqual(args.connection, "usb")

    def test_port_and_baud_fall_back_to_protocol_defaults_when_nothing_saved(self):
        with _patch_saved({}):
            args = parse_args(["--demo"])
        self.assertEqual(args.port, 14551)
        self.assertEqual(args.baud, 420000)

    def test_uses_saved_values_when_present(self):
        saved = {
            "protocol": "mavlink",
            "connection": "udp",
            "host": "192.168.1.5",
            "port": 9999,
            "udp_mode": "connect",
            "serial_port": "COM7",
            "baud": 115200,
        }
        with _patch_saved(saved):
            args = parse_args(["--demo"])
        self.assertEqual(args.protocol, "mavlink")
        self.assertEqual(args.connection, "udp")
        self.assertEqual(args.host, "192.168.1.5")
        self.assertEqual(args.port, 9999)
        self.assertEqual(args.udp_mode, "connect")
        self.assertEqual(args.serial_port, "COM7")
        self.assertEqual(args.baud, 115200)

    def test_explicit_cli_flag_overrides_saved_value(self):
        saved = {"protocol": "mavlink", "connection": "udp"}
        with _patch_saved(saved):
            args = parse_args(["--demo", "--protocol", "crsf"])
        self.assertEqual(args.protocol, "crsf")
        # Untouched fields still come from the saved settings.
        self.assertEqual(args.connection, "udp")

    def test_plain_launch_with_default_usb_and_no_saved_port_does_not_error(self):
        # This is the normal GUI double-click case (no CLI flags at all) -
        # it must never raise, since the startup connection dialog is what
        # lets the user actually pick a port, not the argument parser.
        with _patch_saved({}):
            args = parse_args([])
        self.assertEqual(args.connection, "usb")
        self.assertEqual(args.serial_port, "")

    def test_explicit_usb_without_serial_port_still_errors(self):
        with _patch_saved({}):
            with self.assertRaises(SystemExit):
                parse_args(["--connection", "usb"])

    def test_explicit_usb_without_serial_port_but_demo_does_not_error(self):
        with _patch_saved({}):
            args = parse_args(["--connection", "usb", "--demo"])
        self.assertEqual(args.connection, "usb")

    def test_explicit_usb_with_saved_serial_port_does_not_error(self):
        with _patch_saved({"serial_port": "COM3"}):
            args = parse_args(["--connection", "usb"])
        self.assertEqual(args.serial_port, "COM3")


if __name__ == "__main__":
    unittest.main()
