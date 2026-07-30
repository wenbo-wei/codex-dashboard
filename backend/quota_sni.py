"""Legacy StatusNotifierItem and headless presentation adapters."""

from __future__ import annotations

import datetime as dt
import math
import os
import sys
from typing import Any

import dbus
import dbus.service
from gi.repository import Gio, GLib


APP_ID = "codex-quota"
BUS_NAME = f"org.kde.StatusNotifierItem-{os.getpid()}-1"
WATCHER_NAME = "org.kde.StatusNotifierWatcher"
WATCHER_PATH = "/StatusNotifierWatcher"
WATCHER_INTERFACE = "org.kde.StatusNotifierWatcher"
NOTIFICATIONS_NAME = "org.freedesktop.Notifications"
NOTIFICATIONS_PATH = "/org/freedesktop/Notifications"
NOTIFICATIONS_INTERFACE = "org.freedesktop.Notifications"
ITEM_INTERFACE = "org.kde.StatusNotifierItem"
MENU_INTERFACE = "com.canonical.dbusmenu"
ITEM_PATH = "/StatusNotifierItem"
MENU_PATH = "/MenuBar"


def _rounded_percent(value: float) -> int:
    return int(math.floor(value + 0.5))


def format_panel_label(snapshot: dict[str, Any] | None) -> str:
    if not snapshot or not snapshot.get("limits"):
        return "Codex --%"
    active_limit = min(
        snapshot["limits"],
        key=lambda limit_data: float(limit_data["remaining_percent"]),
    )
    remaining = _rounded_percent(float(active_limit["remaining_percent"]))
    return f"Codex {remaining}%"


def format_refresh_label(base_label: str, frame: str) -> str:
    del base_label
    return f"Codex {frame}"


def format_reset_time(timestamp: int | None) -> str:
    """Format a quota reset timestamp in the desktop's local timezone."""
    if timestamp is None:
        return "Time unknown"
    reset_time = dt.datetime.fromtimestamp(timestamp).astimezone()
    return reset_time.strftime("%b %-d, %H:%M")


def build_menu_items(
    snapshot: dict[str, Any] | None,
) -> list[tuple[int, str, bool]]:
    """Build stable quota-detail and action rows for the Codex menu."""
    items: list[tuple[int, str, bool]] = []
    if snapshot and snapshot.get("limits"):
        active_limit = min(
            snapshot["limits"],
            key=lambda limit_data: float(limit_data["remaining_percent"]),
        )
        items.append(
            (
                2,
                (
                    "Refreshes: "
                    f"{format_reset_time(active_limit.get('resets_at'))}"
                ),
                True,
            )
        )
    items.append((11, "ChatGPT", True))
    return items


class LinkDbusMenu(dbus.service.Object):
    """Codex quota details and links exposed through DBusMenu."""

    def __init__(self, bus_name: dbus.service.BusName) -> None:
        super().__init__(bus_name, MENU_PATH)
        self._properties = {
            "Version": dbus.UInt32(4),
            "TextDirection": dbus.String("ltr"),
            "Status": dbus.String("normal"),
            "IconThemePath": dbus.Array([], signature="s"),
        }
        self._revision = 1
        self._items = build_menu_items(None)

    def set_snapshot(self, snapshot: dict[str, Any] | None) -> None:
        items = build_menu_items(snapshot)
        if items == self._items:
            return
        self._items = items
        self._revision += 1
        self.LayoutUpdated(self._revision, 0)

    @staticmethod
    def _item_properties(
        label: str,
        enabled: bool,
    ) -> dbus.Dictionary:
        return dbus.Dictionary(
            {
                "label": dbus.String(label),
                "enabled": dbus.Boolean(enabled),
                "visible": dbus.Boolean(True),
            },
            signature="sv",
        )

    def _layout_item(
        self,
        item_id: int,
        label: str,
        enabled: bool,
    ) -> dbus.Struct:
        return dbus.Struct(
            (
                dbus.Int32(item_id),
                self._item_properties(label, enabled),
                dbus.Array([], signature="v"),
            ),
            signature="ia{sv}av",
            variant_level=1,
        )

    @dbus.service.method(
        dbus.PROPERTIES_IFACE,
        in_signature="ss",
        out_signature="v",
    )
    def Get(self, interface: str, name: str) -> Any:
        if interface != MENU_INTERFACE or name not in self._properties:
            raise dbus.exceptions.DBusException(
                f"Unknown property {interface}.{name}",
                name="org.freedesktop.DBus.Error.UnknownProperty",
            )
        return self._properties[name]

    @dbus.service.method(
        dbus.PROPERTIES_IFACE,
        in_signature="s",
        out_signature="a{sv}",
    )
    def GetAll(self, interface: str) -> dbus.Dictionary:
        if interface != MENU_INTERFACE:
            return dbus.Dictionary({}, signature="sv")
        return dbus.Dictionary(self._properties, signature="sv")

    @dbus.service.method(
        dbus.PROPERTIES_IFACE,
        in_signature="ssv",
        out_signature="",
    )
    def Set(self, interface: str, name: str, value: Any) -> None:
        del interface, name, value
        raise dbus.exceptions.DBusException(
            "Properties are read-only",
            name="org.freedesktop.DBus.Error.PropertyReadOnly",
        )

    @dbus.service.method(
        MENU_INTERFACE,
        in_signature="iias",
        out_signature="u(ia{sv}av)",
    )
    def GetLayout(
        self,
        parent_id: int,
        recursion_depth: int,
        property_names: list[str],
    ):
        del parent_id, recursion_depth, property_names
        properties = dbus.Dictionary(
            {"children-display": dbus.String("submenu")},
            signature="sv",
        )
        children = dbus.Array(
            [
                self._layout_item(item_id, label, enabled)
                for item_id, label, enabled in self._items
            ],
            signature="v",
        )
        layout = dbus.Struct(
            (dbus.Int32(0), properties, children),
            signature="ia{sv}av",
        )
        return dbus.UInt32(self._revision), layout

    @dbus.service.method(
        MENU_INTERFACE,
        in_signature="aias",
        out_signature="a(ia{sv})",
    )
    def GetGroupProperties(
        self,
        ids: list[int],
        property_names: list[str],
    ):
        del property_names
        requested = {int(item_id) for item_id in ids}
        results = [
            dbus.Struct(
                (
                    dbus.Int32(item_id),
                    self._item_properties(label, enabled),
                ),
                signature="ia{sv}",
            )
            for item_id, label, enabled in self._items
            if not requested or item_id in requested
        ]
        return dbus.Array(results, signature="(ia{sv})")

    @dbus.service.method(
        MENU_INTERFACE,
        in_signature="is",
        out_signature="v",
    )
    def GetProperty(self, item_id: int, name: str):
        for candidate_id, label, enabled in self._items:
            if candidate_id == item_id:
                return self._item_properties(label, enabled).get(
                    name,
                    dbus.String(""),
                )
        return dbus.String("")

    @dbus.service.method(
        MENU_INTERFACE,
        in_signature="isvu",
        out_signature="",
    )
    def Event(
        self,
        item_id: int,
        event_id: str,
        data: Any,
        timestamp: int,
    ) -> None:
        del data, timestamp
        if event_id != "clicked":
            return
        try:
            if item_id == 11:
                Gio.AppInfo.launch_default_for_uri(
                    "https://chatgpt.com/",
                    None,
                )
        except GLib.Error as error:
            print(
                f"codex-quota: cannot open menu target: {error.message}",
                file=sys.stderr,
            )

    @dbus.service.method(
        MENU_INTERFACE,
        in_signature="a(isvu)",
        out_signature="ai",
    )
    def EventGroup(self, events: list[Any]):
        del events
        return dbus.Array([], signature="i")

    @dbus.service.method(
        MENU_INTERFACE,
        in_signature="i",
        out_signature="b",
    )
    def AboutToShow(self, item_id: int) -> bool:
        del item_id
        return False

    @dbus.service.method(
        MENU_INTERFACE,
        in_signature="ai",
        out_signature="aiai",
    )
    def AboutToShowGroup(self, ids: list[int]):
        del ids
        return dbus.Array([], signature="i"), dbus.Array([], signature="i")

    @dbus.service.signal(MENU_INTERFACE, signature="ui")
    def LayoutUpdated(self, revision: int, parent: int) -> None:
        del revision, parent


class StatusNotifierItem(dbus.service.Object):
    def __init__(
        self,
        bus_name: dbus.service.BusName,
        refresh_callback,
    ) -> None:
        super().__init__(bus_name, ITEM_PATH)
        self._refresh_callback = refresh_callback
        self._properties = {
            "Category": dbus.String("ApplicationStatus"),
            "Id": dbus.String(APP_ID),
            "Title": dbus.String("Codex remaining quota"),
            "Status": dbus.String("Active"),
            "WindowId": dbus.Int32(0),
            "IconThemePath": dbus.String(""),
            "Menu": dbus.ObjectPath(MENU_PATH),
            "ItemIsMenu": dbus.Boolean(True),
            "IconName": dbus.String("codex-dashboard-symbolic"),
            "IconPixmap": dbus.Array([], signature="(iiay)"),
            "OverlayIconName": dbus.String(""),
            "OverlayIconPixmap": dbus.Array([], signature="(iiay)"),
            "AttentionIconName": dbus.String("dialog-warning-symbolic"),
            "AttentionIconPixmap": dbus.Array([], signature="(iiay)"),
            "AttentionMovieName": dbus.String(""),
            "IconAccessibleDesc": dbus.String("Codex remaining quota"),
            "AttentionAccessibleDesc": dbus.String(
                "Codex quota is low"
            ),
            "XAyatanaLabel": dbus.String("Codex --%"),
            "XAyatanaLabelGuide": dbus.String("Codex 100%"),
        }

    def get_label(self) -> str:
        return str(self._properties["XAyatanaLabel"])

    def set_label(self, label: str) -> None:
        if str(self._properties["XAyatanaLabel"]) == label:
            return
        value = dbus.String(label)
        self._properties["XAyatanaLabel"] = value
        changed = dbus.Dictionary(
            {"XAyatanaLabel": value},
            signature="sv",
        )
        self.PropertiesChanged(
            ITEM_INTERFACE,
            changed,
            dbus.Array([], signature="s"),
        )
        self.XAyatanaNewLabel(
            label,
            str(self._properties["XAyatanaLabelGuide"]),
        )

    @dbus.service.method(
        dbus.PROPERTIES_IFACE,
        in_signature="ss",
        out_signature="v",
    )
    def Get(self, interface: str, name: str) -> Any:
        if interface != ITEM_INTERFACE or name not in self._properties:
            raise dbus.exceptions.DBusException(
                f"Unknown property {interface}.{name}",
                name="org.freedesktop.DBus.Error.UnknownProperty",
            )
        return self._properties[name]

    @dbus.service.method(
        dbus.PROPERTIES_IFACE,
        in_signature="s",
        out_signature="a{sv}",
    )
    def GetAll(self, interface: str) -> dbus.Dictionary:
        if interface != ITEM_INTERFACE:
            return dbus.Dictionary({}, signature="sv")
        return dbus.Dictionary(self._properties, signature="sv")

    @dbus.service.method(
        dbus.PROPERTIES_IFACE,
        in_signature="ssv",
        out_signature="",
    )
    def Set(self, interface: str, name: str, value: Any) -> None:
        del interface, name, value
        raise dbus.exceptions.DBusException(
            "Properties are read-only",
            name="org.freedesktop.DBus.Error.PropertyReadOnly",
        )

    @dbus.service.signal(
        dbus.PROPERTIES_IFACE,
        signature="sa{sv}as",
    )
    def PropertiesChanged(
        self,
        interface: str,
        changed: dict,
        invalidated: list,
    ) -> None:
        del interface, changed, invalidated

    @dbus.service.signal(ITEM_INTERFACE, signature="ss")
    def XAyatanaNewLabel(self, label: str, guide: str) -> None:
        del label, guide

    @dbus.service.method(
        ITEM_INTERFACE,
        in_signature="ii",
        out_signature="",
    )
    def ContextMenu(self, x: int, y: int) -> None:
        del x, y

    @dbus.service.method(
        ITEM_INTERFACE,
        in_signature="ii",
        out_signature="",
    )
    def SecondaryActivate(self, x: int, y: int) -> None:
        del x, y
        self._refresh_callback(force_live=True)

    @dbus.service.method(
        ITEM_INTERFACE,
        in_signature="u",
        out_signature="",
    )
    def XAyatanaSecondaryActivate(self, timestamp: int) -> None:
        del timestamp
        self._refresh_callback(force_live=True)

    @dbus.service.method(
        ITEM_INTERFACE,
        in_signature="s",
        out_signature="",
    )
    def ProvideXdgActivationToken(self, token: str) -> None:
        del token

    @dbus.service.method(
        ITEM_INTERFACE,
        in_signature="is",
        out_signature="",
    )
    def Scroll(self, delta: int, orientation: str) -> None:
        del delta, orientation


class HeadlessMenu:
    """In-memory adapter for the menu seam in headless mode."""

    def set_snapshot(self, snapshot: dict[str, Any] | None) -> None:
        del snapshot


class HeadlessStatusItem:
    """In-memory adapter for label state in headless mode."""

    def __init__(self) -> None:
        self._label = "Codex --%"

    def get_label(self) -> str:
        return self._label

    def set_label(self, label: str) -> None:
        self._label = label
