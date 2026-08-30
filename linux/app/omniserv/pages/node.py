"""Node apps pane: fnm runtime management and managed Node.js application list."""
from __future__ import annotations

import re

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk  # noqa: E402

from ..widgets import PagedList


class _AppsPage(Gtk.Box):
    """Shared base for Node + Python panes (managed runtime + an apps PagedList)."""
    KIND = "node"
    TITLE = "Node apps"

    def __init__(self, win) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12,
                         margin_top=18, margin_bottom=18, margin_start=18, margin_end=18)
        self.win = win
        self.runtime = Adw.PreferencesGroup(title="Runtime")
        self.rt_row = Adw.ActionRow(title="…")
        self.rt_btn = Gtk.Button(valign=Gtk.Align.CENTER, visible=False, css_classes=["suggested-action"])
        self._rt_handler_id = None
        self.rt_row.add_suffix(self.rt_btn)
        self.runtime.add(self.rt_row)
        self.append(self.runtime)
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        header.append(Gtk.Label(label=self.TITLE, xalign=0, hexpand=True, css_classes=["title-4"]))
        add = Gtk.Button(label="Add app", icon_name="list-add-symbolic", css_classes=["suggested-action"])
        add.connect("clicked", lambda *_: self.win.add_site_dialog(default_type=self.KIND))
        header.append(add)
        self.append(header)
        self.list = PagedList(self._row, lambda a, q: q.lower() in a.get("name", "").lower(),
                              page_size=self.win.cfg_int("apps_page_size", 15),
                              empty_text=f"No {self.KIND} apps yet.",
                              on_page_size_changed=lambda n: self.win.set_cfg("apps_page_size", n))
        self.append(self.list)

    def _apps(self):
        rc, out = self.win.engine.run(f"{self.KIND}site", "list")
        apps = []
        for line in out.splitlines():
            line = line.strip()
            # skip blanks + the engine's "no X sites — omniserv … <name> …" help line (the <…>
            # placeholders also break GTK markup), usage lines, and *.test domains.
            low = line.lower()
            if (not line or "<" in line or "omniserv" in low or low.startswith("no ")
                    or "—" in line or "usage" in low or ".test" in line or len(line) <= 1):
                continue
            m = re.search(r"([a-z0-9][a-z0-9._-]*)", line, re.I)
            if m and m.group(1) not in ("python", "node", "site", "app"):
                apps.append({"name": m.group(1), "line": GLib.markup_escape_text(line)})
        return apps

    def _row(self, a: dict) -> Adw.ActionRow:
        name = a["name"]
        row = Adw.ActionRow(title=name, subtitle=a.get("line", ""))
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6, valign=Gtk.Align.CENTER)
        for icon, tip, verb in (("media-playback-start-symbolic", "Start", "start"),
                                 ("media-playback-stop-symbolic", "Stop", "stop"),
                                 ("view-refresh-symbolic", "Restart", "restart")):
            b = Gtk.Button(icon_name=icon, tooltip_text=tip)
            b.connect("clicked", lambda _w, v=verb: self.win.run_verb([f"{self.KIND}site", v, name], f"{v} {name}…"))
            box.append(b)
        rm = Gtk.Button(icon_name="user-trash-symbolic", tooltip_text="Remove", css_classes=["destructive-action"])
        rm.connect("clicked", lambda *_: self.win.run_verb([f"{self.KIND}site", "rm", name], f"Removing {name}…"))
        box.append(rm)
        row.add_suffix(box)
        return row

    def _set_runtime_btn(self, label, handler):
        if self._rt_handler_id:
            self.rt_btn.disconnect(self._rt_handler_id)
            self._rt_handler_id = None
        if not label:
            self.rt_btn.set_visible(False)
            return
        self.rt_btn.set_label(label)
        self._rt_handler_id = self.rt_btn.connect("clicked", lambda *_: handler())
        self.rt_btn.set_visible(True)

    def refresh(self, data: dict) -> None:
        self.list.set_items(self._apps())


class NodePage(_AppsPage):
    KIND, TITLE = "node", "Node apps"

    def refresh(self, data):
        installed = any(s["key"] == "fnm" and s["installed"] for s in data.get("services", []))
        out = self.win.engine.run("node", "list")[1].strip() if installed else ""
        self.rt_row.set_title("Node (fnm)" if installed else "Node — fnm not installed")
        self.rt_row.set_subtitle((out[:80] if out else "Install a Node version to run Node apps")
                                 if installed else "Install fnm, then a Node version, to run Node apps")
        if installed:
            self._set_runtime_btn("Install Node version…", self._install_node)
        else:
            self._set_runtime_btn("Install fnm", lambda: self.win.run_progress(
                ["install", "fnm"], "Installing fnm", "Downloading the Node version manager…", "fnm installed."))
        super().refresh(data)

    def _install_node(self):
        self.win.choose("Install Node", "Pick a version to install and set as default:", ["22", "20", "18"],
                        lambda v: self.win.run_verb(["node", "install", v], f"Installing Node {v}…",
                                                    then=(["node", "use", v], f"Setting Node {v} as default…")))
