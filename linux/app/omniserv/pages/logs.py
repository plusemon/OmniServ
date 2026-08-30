"""Logs pane: system and application log viewer."""
from __future__ import annotations

import os

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402


class LogsPage(Gtk.Box):
    def __init__(self, win) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=10,
                         margin_top=18, margin_bottom=18, margin_start=18, margin_end=18)
        self.win = win
        top = Gtk.Box(spacing=8)
        self.dd = Gtk.DropDown.new_from_strings(["(refresh)"])
        self.dd.connect("notify::selected", lambda *_: self._load())
        top.append(Gtk.Label(label="Log", css_classes=["dim-label"]))
        top.append(self.dd)
        reload_b = Gtk.Button(icon_name="view-refresh-symbolic", tooltip_text="Reload")
        reload_b.connect("clicked", lambda *_: self._load())
        top.append(reload_b)
        self.append(top)
        self.text = Gtk.TextView(editable=False, monospace=True, css_classes=["card"])
        sc = Gtk.ScrolledWindow(vexpand=True)
        sc.set_child(self.text)
        self.append(sc)
        self._files = []

    def refresh(self, data: dict) -> None:
        logdir = os.path.expanduser("~/.omniserv/logs")
        self._files = sorted(os.listdir(logdir)) if os.path.isdir(logdir) else []
        model = Gtk.StringList.new(self._files or ["(no logs yet)"])
        self.dd.set_model(model)
        if self._files:
            self._load()

    def _load(self):
        if not self._files:
            return
        idx = self.dd.get_selected()
        if idx < 0 or idx >= len(self._files):
            return
        path = os.path.expanduser(f"~/.omniserv/logs/{self._files[idx]}")
        try:
            with open(path, errors="replace") as f:
                content = "".join(f.readlines()[-500:])
        except Exception as e:
            content = str(e)
        self.text.get_buffer().set_text(content)
