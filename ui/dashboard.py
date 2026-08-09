"""Telemetry dashboard bar: GPS / link quality / battery / sensors /
long-range / connection status. Which individual fields are shown, the
order the groups appear in, and how many rows they wrap across are all
user-configurable (see DashboardSettingsDialog) and persisted as their
preferred default layout via core.dashboard_config.
"""
from __future__ import annotations

import math
import time
from typing import Dict, List

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QComboBox, QGroupBox, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from core import geo, i18n
from core.dashboard_config import load_dashboard_layout, load_visible_fields
from core.telemetry_state import TelemetryState
from ui import icons

_NA = "--"
NEW_PROFILE_SENTINEL = "__new_model__"

# Glass-cockpit palette - matches the dark panel look the map overlays
# already use, with a cyan "avionics" accent instead of a plain OS theme.
PANEL_BG = "#0a0e13"
GROUP_BG = "#111820"
GROUP_BORDER = "#243040"
ACCENT = "#3ddbc9"
VALUE_COLOR = "#e8fffa"
CAPTION_COLOR = "#7891a3"
CONNECTED_COLOR = "#39d98a"
DISCONNECTED_COLOR = "#ff5f56"
_MONO_FONT = "'Consolas', 'Courier New', monospace"

_GROUP_QSS = f"""
    QGroupBox {{
        background-color: {GROUP_BG};
        border: 1px solid {GROUP_BORDER};
        border-top: 2px solid {ACCENT};
        border-radius: 4px;
        margin-top: 12px;
        padding: 8px 6px 4px 6px;
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        subcontrol-position: top left;
        left: 8px;
        top: -2px;
        padding: 0 5px;
        color: {ACCENT};
        font-size: 9px;
        font-weight: 700;
        background-color: {PANEL_BG};
    }}
"""


def _value_label() -> QLabel:
    lbl = QLabel(_NA)
    lbl.setStyleSheet(f"color: {VALUE_COLOR}; font-family: {_MONO_FONT}; font-weight: 700; font-size: 14px;")
    return lbl


def _icon_label(pixmap) -> QLabel:
    lbl = QLabel()
    lbl.setPixmap(pixmap)
    lbl.setFixedSize(icons.SIZE, icons.SIZE)
    return lbl


class _Field(QWidget):
    def __init__(self, caption_key: str) -> None:
        super().__init__()
        self.caption_key = caption_key
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(0)
        self.caption_label = QLabel(i18n.tr(caption_key))
        self.caption_label.setStyleSheet(f"color: {CAPTION_COLOR}; font-size: 9px; font-weight: 600;")
        self.value = _value_label()
        layout.addWidget(self.caption_label)
        layout.addWidget(self.value)

    def set_text(self, text: str) -> None:
        self.value.setText(text)

    def retranslate(self) -> None:
        self.caption_label.setText(i18n.tr(self.caption_key))

    def set_centered(self, centered: bool) -> None:
        # Left-aligned reads fine in a wide horizontal row, but in a narrow
        # left/right-docked column it leaves a ragged strip of empty space
        # next to every value - centering it there looks tidier.
        align = Qt.AlignmentFlag.AlignHCenter if centered else Qt.AlignmentFlag.AlignLeft
        self.caption_label.setAlignment(align | Qt.AlignmentFlag.AlignVCenter)
        self.value.setAlignment(align | Qt.AlignmentFlag.AlignVCenter)


DEFAULT_ROWS = 1
MAX_ROWS = 4


class Dashboard(QWidget):
    # Emitted on every resize - MainWindow uses this to re-fit a docked
    # artificial horizon (a fixed-aspect gauge that otherwise stays at
    # whatever size it had when docked) to the panel's current width.
    resized = pyqtSignal()

    # Emitted only for user-driven selections (QComboBox.activated, not
    # currentIndexChanged) - so MainWindow can freely repopulate/reselect
    # the combo programmatically (e.g. after saving a new profile, or
    # restoring the last-used one on startup) without that itself
    # re-triggering a profile load.
    model_profile_selected = pyqtSignal(str)
    # Picking the "+ Neues Modell anlegen" entry - MainWindow opens the
    # model-profile dialog's create-new flow in response.
    new_model_profile_requested = pyqtSignal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"Dashboard {{ background-color: {PANEL_BG}; }}" + _GROUP_QSS)
        self._fields: list[_Field] = []
        self._boxes_by_key: Dict[str, QGroupBox] = {}
        self._fields_by_box: dict = {}
        self._icon_by_box: dict = {}
        self._connected = False
        self._visible_fields: set = set()
        self._group_order: List[str] = []
        self._rows = DEFAULT_ROWS
        self._vertical = False

        self._home = None       # (lat, lon) of the first GPS fix this session
        self._flight_start = None  # time.monotonic() at that first fix

        # Fixed wrapper of three sections: an optional top dock row (e.g.
        # the artificial horizon and/or altitude chart, docked in from the
        # map), the field matrix in the middle (apply_layout() rebuilds
        # only this part), and an optional bottom dock (e.g. the waypoint
        # editor). Kept as separate always-present containers rather than
        # inserting docked widgets directly into the matrix layout, since
        # apply_layout() tears down and rebuilds that layout's contents on
        # every field/row/orientation change and would otherwise discard
        # them.
        # Model-profile picker - always visible at the top of the telemetry
        # panel, not just tucked away in a menu dialog, since switching
        # models mid-session (and getting the right battery thresholds
        # applied) is a frequent action, not a rare settings change.
        self._model_label = QLabel()
        self._model_label.setStyleSheet(f"color: {CAPTION_COLOR}; font-size: 10px;")
        self._model_combo = QComboBox()
        self._model_combo.addItem("", "")
        self._last_selected_profile_name = ""
        self._model_combo.activated.connect(self._on_model_combo_activated)
        model_row = QHBoxLayout()
        model_row.setContentsMargins(0, 0, 0, 0)
        model_row.setSpacing(6)
        model_row.addWidget(self._model_label)
        model_row.addWidget(self._model_combo, 1)
        self._model_row_widget = QWidget()
        self._model_row_widget.setLayout(model_row)

        self._top_dock_widget = QWidget()
        self._top_dock_layout = QHBoxLayout(self._top_dock_widget)
        self._top_dock_layout.setContentsMargins(0, 0, 0, 0)
        self._top_dock_layout.setSpacing(8)
        self._top_dock_widget.setVisible(False)

        self._bottom_dock_widget = QWidget()
        self._bottom_dock_layout = QVBoxLayout(self._bottom_dock_widget)
        self._bottom_dock_layout.setContentsMargins(0, 0, 0, 0)
        self._bottom_dock_widget.setVisible(False)

        self._matrix_container = QWidget()
        self._outer = QVBoxLayout(self._matrix_container)
        self._outer.setContentsMargins(0, 0, 0, 0)
        self._outer.setSpacing(4)

        wrapper = QVBoxLayout(self)
        wrapper.setContentsMargins(8, 6, 8, 6)
        wrapper.setSpacing(8)
        wrapper.addWidget(self._model_row_widget)
        wrapper.addWidget(self._top_dock_widget)
        wrapper.addWidget(self._matrix_container, 1)
        wrapper.addWidget(self._bottom_dock_widget)

        self.gps_lat = _Field("dash_lat")
        self.gps_lon = _Field("dash_lon")
        self.gps_alt = _Field("dash_alt")
        self.gps_sats = _Field("dash_sats")
        self._group("dash_gps", [self.gps_lat, self.gps_lon, self.gps_alt, self.gps_sats], icons.gps_icon())

        self.mode = _Field("dash_flight_mode")
        self._group("dash_status", [self.mode], icons.drone_icon())

        self.rssi = _Field("dash_rssi")
        self.lq = _Field("dash_lq")
        self.snr = _Field("dash_snr")
        self.tx_power = _Field("dash_tx_power")
        self.link_icon_label = _icon_label(icons.signal_icon(-1))
        self._group("dash_link", [self.rssi, self.lq, self.snr, self.tx_power], icon_label=self.link_icon_label)

        self.voltage = _Field("dash_voltage")
        self.remaining = _Field("dash_remaining")
        self.min_cell = _Field("dash_min_cell")
        self.battery_current = _Field("dash_battery_current")
        self.battery_capacity_used = _Field("dash_battery_capacity_used")
        self.battery_icon_label = _icon_label(icons.battery_icon(None))
        self._group(
            "dash_battery",
            [self.voltage, self.remaining, self.min_cell, self.battery_current, self.battery_capacity_used],
            icon_label=self.battery_icon_label,
        )

        self.vario = _Field("dash_vario")
        self.baro_alt = _Field("dash_baro_alt")
        self.rpm = _Field("dash_rpm")
        self.temperature = _Field("dash_temperature")
        self._group("dash_sensors", [self.vario, self.baro_alt, self.rpm, self.temperature], icons.sensor_icon())

        self.groundspeed = _Field("dash_groundspeed")
        self.distance_home = _Field("dash_distance_home")
        self.bearing_home = _Field("dash_bearing_home")
        self.flight_timer = _Field("dash_flight_timer")
        self._group(
            "dash_longrange",
            [self.groundspeed, self.distance_home, self.bearing_home, self.flight_timer],
            icons.compass_icon(),
        )

        self.conn_icon_label = _icon_label(icons.status_led_icon(False))
        self.conn_text = QLabel()
        conn_row = QHBoxLayout()
        conn_row.setSpacing(6)
        conn_row.addWidget(self.conn_icon_label)
        conn_row.addWidget(self.conn_text)
        conn_wrap = QWidget()
        conn_wrap.setLayout(conn_row)
        conn_box = QVBoxLayout()
        conn_box.addWidget(conn_wrap)
        conn_group = QGroupBox()
        conn_group.setLayout(conn_box)
        self._boxes_by_key["dash_connection"] = conn_group

        self.set_connection_status(False)

        saved_layout = load_dashboard_layout()
        if saved_layout is not None:
            group_order, rows = saved_layout
        else:
            group_order, rows = list(self._boxes_by_key.keys()), DEFAULT_ROWS
        self.apply_layout(group_order, rows)

        self.retranslate()

        saved = load_visible_fields()
        self.apply_field_visibility(saved if saved is not None else self.all_field_keys())

        i18n.on_language_changed(self.retranslate)

    def _group(self, title_key: str, fields: list, icon_pixmap=None, icon_label: QLabel = None) -> QGroupBox:
        box = QGroupBox()
        self._boxes_by_key[title_key] = box
        layout = QHBoxLayout(box)
        layout.setSpacing(10)
        if icon_label is None and icon_pixmap is not None:
            icon_label = _icon_label(icon_pixmap)
        if icon_label is not None:
            layout.addWidget(icon_label)
            self._icon_by_box[box] = icon_label
        self._fields_by_box[box] = list(fields)
        for f in fields:
            layout.addWidget(f)
            self._fields.append(f)
        return box

    def _rebuild_box_layout(self, box: QGroupBox, vertical: bool) -> None:
        """Swap a group's internal field layout between a horizontal row
        (icon + fields side by side - the default, for a top/bottom-docked
        dashboard) and a vertical stack (for a left/right-docked one, where
        a wide row would just overflow a narrow column)."""
        old_layout = box.layout()
        if old_layout is not None:
            while old_layout.count():
                old_layout.takeAt(0)
            # Qt only allows setLayout() once per widget - steal the old
            # (now-empty) layout onto a throwaway widget so it detaches.
            QWidget().setLayout(old_layout)

        new_layout = QVBoxLayout() if vertical else QHBoxLayout()
        new_layout.setSpacing(6 if vertical else 10)
        icon_label = self._icon_by_box.get(box)
        if icon_label is not None:
            new_layout.addWidget(icon_label, 0, Qt.AlignmentFlag.AlignHCenter if vertical else Qt.AlignmentFlag(0))
        for f in self._fields_by_box.get(box, []):
            f.set_centered(vertical)
            new_layout.addWidget(f)
        box.setLayout(new_layout)

    def set_vertical(self, vertical: bool) -> None:
        """Reflow every group's fields (and the row/column grouping) between
        horizontal (top/bottom dock) and vertical (left/right dock)."""
        if vertical == self._vertical:
            return
        self._vertical = vertical
        for box in self._boxes_by_key.values():
            if box in self._fields_by_box:
                self._rebuild_box_layout(box, vertical)
        self.apply_layout(self._group_order, self._rows)

    def set_top_docked(self, widget: QWidget, docked: bool) -> None:
        """Embed (or remove) a widget in the row above the field matrix -
        used for the artificial horizon and the altitude chart, which the
        caller (MainWindow) otherwise floats as map overlays."""
        if docked:
            widget.setParent(self._top_dock_widget)
            self._top_dock_layout.addWidget(widget)
            widget.show()
        else:
            self._top_dock_layout.removeWidget(widget)
        self._top_dock_widget.setVisible(self._top_dock_layout.count() > 0)

    def set_bottom_docked(self, widget: QWidget, docked: bool) -> None:
        """Embed (or remove) a widget in the section below the field
        matrix - used for the waypoint editor."""
        if docked:
            widget.setParent(self._bottom_dock_widget)
            self._bottom_dock_layout.addWidget(widget)
            widget.show()
        else:
            self._bottom_dock_layout.removeWidget(widget)
        self._bottom_dock_widget.setVisible(self._bottom_dock_layout.count() > 0)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.resized.emit()

    # ------------------------------------------------------- configuration

    def field_catalog(self) -> list:
        """[(group_title_key, [field_caption_key, ...]), ...] for the settings
        dialog, in the dashboard's current display order."""
        return [
            (key, [f.caption_key for f in self._fields_by_box.get(self._boxes_by_key[key], [])])
            for key in self._group_order
            if self._fields_by_box.get(self._boxes_by_key.get(key))
        ]

    def all_field_keys(self) -> set:
        return {f.caption_key for f in self._fields}

    def visible_fields(self) -> set:
        return set(self._visible_fields)

    def apply_field_visibility(self, keys: set) -> None:
        self._visible_fields = set(keys)
        for f in self._fields:
            f.setVisible(f.caption_key in self._visible_fields)
        for box, fields in self._fields_by_box.items():
            box.setVisible(any(f.caption_key in self._visible_fields for f in fields))
        self._apply_uniform_field_width()

    def _apply_uniform_field_width(self) -> None:
        """Give every field the same minimum width (the widest visible
        one's natural size) so the grid reads as a tidy, symmetric table
        instead of ragged columns sized by whichever caption happens to be
        longest in that particular group."""
        visible = [f for f in self._fields if f.caption_key in self._visible_fields]
        if not visible:
            return
        uniform_width = max(f.sizeHint().width() for f in visible)
        for f in self._fields:
            f.setMinimumWidth(uniform_width)

    def group_order(self) -> List[str]:
        return list(self._group_order)

    def rows(self) -> int:
        return self._rows

    def apply_layout(self, group_order: List[str], rows: int) -> None:
        """Re-arrange the group boxes into `rows` rows (or, when docked
        left/right - see set_vertical() - `rows` side-by-side columns), in
        `group_order`. Any group missing from a stale/incomplete saved
        order is appended at the end rather than dropped, so newly added
        groups stay visible."""
        ordered_keys = [k for k in group_order if k in self._boxes_by_key]
        ordered_keys += [k for k in self._boxes_by_key if k not in ordered_keys]
        self._group_order = ordered_keys
        boxes = [self._boxes_by_key[k] for k in ordered_keys]

        for box in boxes:
            box.setParent(None)

        # The outer container itself only needs rebuilding when the
        # top/bottom vs. left/right orientation actually changed (Qt only
        # allows one setLayout() per widget) - otherwise just clear and
        # refill the existing one, exactly as before orientation support.
        wanted_outer_cls = QHBoxLayout if self._vertical else QVBoxLayout
        if not isinstance(self._outer, wanted_outer_cls):
            old_outer = self._outer
            while old_outer.count():
                item = old_outer.takeAt(0)
                w = item.widget()
                if w is not None:
                    w.deleteLater()
            QWidget().setLayout(old_outer)
            self._outer = wanted_outer_cls()
            self._outer.setContentsMargins(0, 0, 0, 0)
            self._outer.setSpacing(4)
            self._matrix_container.setLayout(self._outer)
        else:
            while self._outer.count():
                item = self._outer.takeAt(0)
                w = item.widget()
                if w is not None:
                    w.deleteLater()

        if self._vertical and boxes:
            # In a narrow docked column, boxes with different caption
            # lengths end up different widths and look ragged side by
            # side - pad every box's group to the widest one's natural
            # width instead.
            uniform_width = max(box.sizeHint().width() for box in boxes)
            for box in boxes:
                box.setMinimumWidth(uniform_width)
        else:
            for box in boxes:
                box.setMinimumWidth(0)

        self._rows = max(1, min(rows, len(boxes) or 1))
        chunk_size = max(1, math.ceil(len(boxes) / self._rows)) if boxes else 1
        chunks = [boxes[i:i + chunk_size] for i in range(0, len(boxes), chunk_size)] or [[]]
        lane_cls = QVBoxLayout if self._vertical else QHBoxLayout
        for chunk in chunks:
            lane_widget = QWidget()
            lane_layout = lane_cls(lane_widget)
            lane_layout.setContentsMargins(0, 0, 0, 0)
            lane_layout.setSpacing(12)
            for box in chunk:
                lane_layout.addWidget(box)
            lane_layout.addStretch(1)
            self._outer.addWidget(lane_widget)

        self._apply_uniform_field_width()

    # ------------------------------------------------------------ profiles

    def _on_model_combo_activated(self, index: int) -> None:
        name = self._model_combo.itemData(index)
        if name == NEW_PROFILE_SENTINEL:
            # An action, not a persistent selection - snap the combo back to
            # whatever was actually selected before, and let MainWindow open
            # the model-creation dialog in response.
            self.set_current_model_profile_name(self._last_selected_profile_name)
            self.new_model_profile_requested.emit()
        elif name:
            self.model_profile_selected.emit(name)

    def set_model_profile_names(self, names: List[str]) -> None:
        """Repopulate the dropdown (e.g. after a profile was saved/deleted
        in the model-profile dialog), preserving the current selection if
        it still exists."""
        current = self.current_model_profile_name()
        self._model_combo.blockSignals(True)
        self._model_combo.clear()
        self._model_combo.addItem(i18n.tr("dashboard_model_none"), "")
        for name in sorted(names):
            self._model_combo.addItem(name, name)
        self._model_combo.addItem(i18n.tr("dashboard_model_new"), NEW_PROFILE_SENTINEL)
        self.set_current_model_profile_name(current)
        self._model_combo.blockSignals(False)

    def current_model_profile_name(self) -> str:
        data = self._model_combo.currentData()
        return data if data and data != NEW_PROFILE_SENTINEL else ""

    def set_current_model_profile_name(self, name: str) -> None:
        self._last_selected_profile_name = name
        index = self._model_combo.findData(name)
        self._model_combo.setCurrentIndex(index if index >= 0 else 0)

    # ------------------------------------------------------------- session

    def reset_session(self) -> None:
        self._home = None
        self._flight_start = None

    def retranslate(self) -> None:
        for key, box in self._boxes_by_key.items():
            box.setTitle(i18n.tr(key))
        for field in self._fields:
            field.retranslate()
        self.set_connection_status(self._connected)
        self._model_label.setText(i18n.tr("dashboard_model_label"))
        self._model_combo.setItemText(0, i18n.tr("dashboard_model_none"))

    def update_state(self, state: TelemetryState) -> None:
        self.gps_lat.set_text(f"{state.lat:.6f}" if state.lat is not None else _NA)
        self.gps_lon.set_text(f"{state.lon:.6f}" if state.lon is not None else _NA)
        self.gps_alt.set_text(f"{state.alt:.1f}" if state.alt is not None else _NA)
        self.gps_sats.set_text(str(state.satellites) if state.satellites is not None else _NA)

        self.mode.set_text(state.flight_mode or _NA)

        self.rssi.set_text(str(state.rssi) if state.rssi is not None else _NA)
        self.lq.set_text(str(state.link_quality) if state.link_quality is not None else _NA)
        self.snr.set_text(f"{state.snr:.1f}" if state.snr is not None else _NA)
        self.tx_power.set_text(str(state.tx_power) if state.tx_power is not None else _NA)

        link_level = -1 if state.link_quality is None else max(0, min(4, math.ceil(state.link_quality / 25)))
        self.link_icon_label.setPixmap(icons.signal_icon(link_level))

        self.voltage.set_text(f"{state.battery_voltage:.2f}" if state.battery_voltage is not None else _NA)
        self.remaining.set_text(str(state.battery_remaining) if state.battery_remaining is not None else _NA)
        self.min_cell.set_text(f"{min(state.cell_voltages):.2f}" if state.cell_voltages else _NA)
        self.battery_current.set_text(f"{state.battery_current:.1f}" if state.battery_current is not None else _NA)
        self.battery_capacity_used.set_text(
            f"{state.battery_capacity_used:.0f}" if state.battery_capacity_used is not None else _NA
        )
        self.battery_icon_label.setPixmap(icons.battery_icon(state.battery_remaining))

        self.vario.set_text(f"{state.vario:+.1f}" if state.vario is not None else _NA)
        self.baro_alt.set_text(f"{state.baro_altitude:.1f}" if state.baro_altitude is not None else _NA)
        self.rpm.set_text(str(state.rpm) if state.rpm is not None else _NA)
        self.temperature.set_text(f"{state.temperature:.1f}" if state.temperature is not None else _NA)

        self.groundspeed.set_text(f"{state.groundspeed * 3.6:.1f}" if state.groundspeed is not None else _NA)

        if state.has_gps_fix():
            if self._home is None:
                self._home = (state.lat, state.lon)
                self._flight_start = time.monotonic()
            dist = geo.haversine_distance_m(state.lat, state.lon, *self._home)
            bearing = geo.bearing_deg(state.lat, state.lon, *self._home)
            self.distance_home.set_text(f"{dist:.0f}")
            self.bearing_home.set_text(f"{bearing:.0f}°")
        else:
            self.distance_home.set_text(_NA)
            self.bearing_home.set_text(_NA)

        if self._flight_start is not None:
            elapsed = int(time.monotonic() - self._flight_start)
            self.flight_timer.set_text(f"{elapsed // 60:02d}:{elapsed % 60:02d}")
        else:
            self.flight_timer.set_text(_NA)

        self.set_connection_status(state.connected)

    def set_connection_status(self, connected: bool) -> None:
        self._connected = connected
        self.conn_icon_label.setPixmap(icons.status_led_icon(connected))
        color = CONNECTED_COLOR if connected else DISCONNECTED_COLOR
        self.conn_text.setStyleSheet(f"color: {color}; font-family: {_MONO_FONT}; font-weight: 700; font-size: 13px;")
        self.conn_text.setText(i18n.tr("dash_connected" if connected else "dash_disconnected"))
