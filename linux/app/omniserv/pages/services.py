"""Services pane: service status list with install, start/stop, autostart, update, and uninstall."""
from __future__ import annotations

import os
import shutil
import subprocess

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk  # noqa: E402

from ..widgets import status_dot
from ._shared import SERVICE_GROUPS, _open_text_editor, clean_version


class ServicesPage(Gtk.Box):
    def __init__(self, win) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12,
                         margin_top=18, margin_bottom=18, margin_start=18, margin_end=18)
        self.win = win
        self.scroller = Gtk.ScrolledWindow(vexpand=True)
        self.body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        self.scroller.set_child(self.body)
        self.append(self.scroller)

    def refresh(self, data: dict) -> None:
        services = data.get("services", [])
        # Only rebuild when something actually changed — otherwise the 4s auto-refresh would
        # tear down + re-add every row and snap your scroll position back to the top.
        sig = tuple((s["key"], s["installed"], s.get("running"), s.get("enabled"), s.get("version", ""))
                    for s in services)
        if sig == getattr(self, "_sig", None):
            return
        self._sig = sig
        adj = self.scroller.get_vadjustment()
        pos = adj.get_value() if adj else 0.0
        child = self.body.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self.body.remove(child)
            child = nxt
        for title, roles in SERVICE_GROUPS:
            group_svcs = [s for s in services if s["role"] in roles.split()]
            if not group_svcs:
                continue
            grp = Adw.PreferencesGroup(title=title)
            for s in group_svcs:
                grp.add(self._row(s))
            self.body.append(grp)
        if adj and pos:   # restore scroll after the new content is laid out
            GLib.idle_add(lambda a=adj, p=pos: (a.set_value(p), False)[1])

    def _row(self, s: dict) -> Adw.ActionRow:
        installed, running = s["installed"], s.get("running")
        sub = clean_version(s.get("version", "")) or s.get("formula", "")
        row = Adw.ActionRow(title=s["key"], subtitle=sub)
        row.add_prefix(status_dot(running))

        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6, valign=Gtk.Align.CENTER)
        key = s["key"]
        if not installed:
            b = Gtk.Button(label="Install", css_classes=["suggested-action"])
            b.connect("clicked", lambda *_, k=key: self.win.run_progress(
                ["install", k], f"Installing {k}",
                f"Downloading and setting up {k} — this can take a minute for larger packages…",
                f"{k} installed."))
            box.append(b)
        else:
            if s["role"] in ("php", "web", "db", "cache", "mail"):
                if running:
                    b = Gtk.Button(icon_name="media-playback-stop-symbolic", tooltip_text="Stop")
                    b.connect("clicked", lambda *_: self.win.run_verb(["stop", key], f"Stopping {key}…"))
                else:
                    b = Gtk.Button(icon_name="media-playback-start-symbolic", tooltip_text="Start")
                    b.connect("clicked", lambda *_: self.win.run_verb(["start", key], f"Starting {key}…"))
                box.append(b)
            star = Gtk.ToggleButton(icon_name="starred-symbolic", tooltip_text="Auto-start",
                                    active=s.get("enabled", False), css_classes=["bh-star"])
            star.connect("toggled", lambda btn: self.win.run_verb(
                ["enable" if btn.get_active() else "disable", key], None, refresh=True))
            box.append(star)
            upd = Gtk.Button(icon_name="software-update-available-symbolic", tooltip_text="Update to latest")
            upd.connect("clicked", lambda *_: self.win.run_verb(["update", key], f"Updating {key}…"))
            box.append(upd)
            if s["role"] == "php":
                ini = Gtk.Button(icon_name="document-edit-symbolic", tooltip_text="Edit php.ini")
                ini.connect("clicked", lambda *_: self._edit_ini(key))
                box.append(ini)
            rm = Gtk.Button(icon_name="user-trash-symbolic", tooltip_text="Uninstall", css_classes=["destructive-action"])
            rm.connect("clicked", lambda *_: self.win.confirm(
                f"Uninstall {key}?", "The service binary is removed; your data and configs stay.",
                lambda: self.win.run_verb(["uninstall", key], f"Uninstalling {key}…")))
            box.append(rm)
        row.add_suffix(box)
        return row

    def _edit_ini(self, key: str) -> None:
        rc, out = self.win.engine.run("php", "ini", "path", key.replace("php@", ""))
        path = out.strip().splitlines()[-1].strip() if out.strip() else ""
        if path and os.path.exists(path):
            _open_text_editor(path)
        else:
            self.win.toast("Couldn't resolve php.ini path")
