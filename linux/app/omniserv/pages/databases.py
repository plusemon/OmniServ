"""Databases pane: database servers, MariaDB/MySQL/PostgreSQL database management, and root password configuration."""
from __future__ import annotations

import json

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk  # noqa: E402

from ..widgets import PagedList, status_dot
from ._shared import clean_version


class DatabasesPage(Gtk.Box):
    def __init__(self, win) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12,
                         margin_top=18, margin_bottom=18, margin_start=18, margin_end=18)
        self.win = win
        self.servers = Adw.PreferencesGroup(title="Database servers")
        self.append(self.servers)
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        header.append(Gtk.Label(label="Databases", xalign=0, hexpand=True, css_classes=["title-4"]))
        add = Gtk.Button(label="Create database", icon_name="list-add-symbolic", css_classes=["suggested-action"])
        add.connect("clicked", lambda *_: self.win.create_db_dialog())
        header.append(add)
        self.append(header)
        self.list = PagedList(self._db_row,
                              lambda d, q: q.lower() in d.get("name", "").lower(),
                              page_size=self.win.cfg_int("databases_page_size", 15),
                              empty_text="No databases yet.",
                              on_page_size_changed=lambda n: self.win.set_cfg("databases_page_size", n))
        self.append(self.list)

    def refresh(self, data: dict) -> None:
        child = self.servers.get_first_child()
        # PreferencesGroup: clear by tracking rows
        for s in [x for x in data.get("services", []) if x["role"] == "db"]:
            pass
        self._render_servers(data)
        self._render_dbs(data)

    def _render_servers(self, data):
        new = Adw.PreferencesGroup(title="Database servers")
        db_svcs = [x for x in data.get("services", []) if x["role"] == "db"]
        # root-password state (MySQL/MariaDB only) — one quick query when a server is up
        my_running = any(s["key"] in ("mariadb", "mysql") and s.get("running") for s in db_svcs)
        root_status = ""
        if my_running:
            _rc, out = self.win.engine.run("db", "root-status")
            root_status = (out.strip().splitlines()[-1].strip() if out.strip() else "")
        for s in db_svcs:
            key = s["key"]
            is_my = key in ("mariadb", "mysql")
            sub = clean_version(s.get("version", "")) or s["formula"]
            if is_my and s.get("running") and root_status in ("set", "blank"):
                sub += " · " + ("password set" if root_status == "set" else "no password")
            row = Adw.ActionRow(title=key, subtitle=sub)
            row.add_prefix(status_dot(s.get("running")))
            box = Gtk.Box(spacing=6, valign=Gtk.Align.CENTER)
            if not s["installed"]:
                b = Gtk.Button(label="Install", css_classes=["suggested-action"])
                b.connect("clicked", lambda _w, k=key: self.win.run_progress(
                    ["install", k], f"Installing {k}",
                    f"Downloading and setting up {k}. This can take a minute…", f"{k} installed."))
                box.append(b)
            else:
                verb = "stop" if s.get("running") else "start"
                icon = "media-playback-stop-symbolic" if s.get("running") else "media-playback-start-symbolic"
                b = Gtk.Button(icon_name=icon, tooltip_text=verb.title())
                b.connect("clicked", lambda _w, k=key, v=verb: self.win.run_verb([v, k], f"{v} {k}…"))
                box.append(b)
                if is_my and s.get("running"):
                    rb = Gtk.Button(label="Root password…", valign=Gtk.Align.CENTER)
                    rb.connect("clicked", lambda *_: self.win.db_root_dialog())
                    box.append(rb)
            row.add_suffix(box)
            new.add(row)
        parent = self.servers.get_parent()
        if parent:
            parent.remove(self.servers)
            parent.insert_child_after(new, None)
        self.servers = new

    def _db_row(self, item):
        name = item.get("name", "")
        engine = item.get("engine", "mysql")
        row = Adw.ActionRow(title=name,
                            subtitle="PostgreSQL" if engine == "pg" else "MariaDB / MySQL")
        box = Gtk.Box(spacing=6, valign=Gtk.Align.CENTER)
        if engine != "pg":
            pb = Gtk.Button(label="Password…", valign=Gtk.Align.CENTER)
            pb.connect("clicked", lambda *_, n=name: self.win.db_password_dialog(n))
            box.append(pb)
        drop = Gtk.Button(label="Drop", valign=Gtk.Align.CENTER, css_classes=["destructive-action"])
        drop.connect("clicked", lambda *_, n=name, e=engine: self.win.db_drop(n, e))
        box.append(drop)
        row.add_suffix(box)
        return row

    def _render_dbs(self, data):
        _rc, out = self.win.engine.run("db", "list", "--json")
        items = []
        if "[" in out:
            try:
                items = json.loads(out[out.find("["):out.rfind("]") + 1])
            except Exception:
                items = []
        self.list.set_items(items)
