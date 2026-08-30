"""Settings pane: startup, updates, page sizes, new site defaults, and About dialog."""
from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk  # noqa: E402

from ..widgets import PAGE_SIZES, page_size_to_int
from ._shared import PHP_KEYS


class SettingsPage(Gtk.Box):
    def __init__(self, win) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=16,
                         margin_top=18, margin_bottom=18, margin_start=18, margin_end=18)
        self.win = win
        self._syncing = False   # True while refresh() sets switch states — see _toggle_autostart
        sc = Gtk.ScrolledWindow(vexpand=True)
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        sc.set_child(body)
        self.append(sc)

        g1 = Adw.PreferencesGroup(title="Startup and updates")
        self.autostart = Adw.SwitchRow(title="Start OmniServ at login",
                                       subtitle="Starts the services at boot + shows the tray at login")
        self.autostart.connect("notify::active", self._toggle_autostart)
        g1.add(self.autostart)
        self.autoupdate = Adw.SwitchRow(title="Check for updates automatically",
                                        active=self.win.cfg_bool("auto_update", True))
        self.autoupdate.connect("notify::active",
                                lambda r, _p: self.win.set_cfg("auto_update", r.get_active()))
        g1.add(self.autoupdate)
        check_row = Adw.ActionRow(title="Check for updates now",
                                  subtitle=f"Current version {self.win.app_version}")
        check_btn = Gtk.Button(label="Check", valign=Gtk.Align.CENTER)
        check_btn.connect("clicked", lambda *_: self.win.check_updates(force=True))
        check_row.add_suffix(check_btn)
        g1.add(check_row)
        body.append(g1)

        g2 = Adw.PreferencesGroup(title="List sizes", description="Rows per page in each list")
        self.sizes = {}
        for key, label, dflt in (("dashboard_page_size", "Dashboard websites", 5),
                                  ("sites_page_size", "Sites", 15),
                                  ("databases_page_size", "Databases", 15),
                                  ("apps_page_size", "Node / Python apps", 15)):
            r = Adw.ComboRow(title=label, model=Gtk.StringList.new(PAGE_SIZES))
            cur = self.win.cfg_int(key, dflt)
            try:
                r.set_selected(PAGE_SIZES.index("All" if cur >= 10 ** 8 else str(cur)))
            except ValueError:
                r.set_selected(1)
            r.connect("notify::selected", lambda row, _p, k=key: self.win.set_cfg(
                k, page_size_to_int(PAGE_SIZES[row.get_selected()])))
            self.sizes[key] = r
            g2.add(r)
        body.append(g2)

        g3 = Adw.PreferencesGroup(title="Defaults for new sites")
        self.default_php = Adw.ComboRow(title="Default PHP", model=Gtk.StringList.new(
            [k.replace("php@", "") for k in PHP_KEYS]))
        self.default_php.connect("notify::selected", lambda row, _p: self.win.engine.run(
            "config", "set", "default_php", [k.replace("php@", "") for k in PHP_KEYS][row.get_selected()]))
        g3.add(self.default_php)
        body.append(g3)

        g4 = Adw.PreferencesGroup(title="About")
        about = Adw.ActionRow(title="OmniServ for Linux",
                              subtitle=f"Version {self.win.app_version} · emon.bd",
                              activatable=True)
        about.add_suffix(Gtk.Image.new_from_icon_name("help-about-symbolic"))
        about.connect("activated", lambda *_: self.win.about())
        g4.add(about)
        body.append(g4)

    def refresh(self, data: dict) -> None:
        # ⚠️ Guard the programmatic set_active: the 4s api-refresh runs while a `loginitem enable`
        # is still waiting at the polkit prompt, so `loginitem` is still false → this would flip the
        # switch back OFF → re-fire notify::active → run `loginitem disable` = a SECOND password
        # prompt for the opposite action. The flag makes _toggle_autostart ignore our own updates.
        self._syncing = True
        self.autostart.set_active(bool(data.get("loginitem")))
        self._syncing = False
        dphp = data.get("config", {}).get("default_php", "8.4")
        try:
            self.default_php.set_selected([k.replace("php@", "") for k in PHP_KEYS].index(dphp))
        except ValueError:
            pass

    def _toggle_autostart(self, row, _p):
        if self._syncing:          # our own refresh() set the state — not a user click
            return
        self.win.run_verb(["loginitem", "enable" if row.get_active() else "disable"], None, refresh=False)
