"""MainWindow — the Adw split-view shell: an 8-item sidebar, a content stack of the 8
panes, a toast overlay, and a 4-second `omniserv api` refresh loop.
"""
from __future__ import annotations

import os
import threading

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk  # noqa: E402

from . import __version__  # noqa: E402
from . import dialogs as D  # noqa: E402
from . import pages as P  # noqa: E402
from . import prefs  # noqa: E402

GUI_CFG = prefs.GUI_CFG

NAV = [
    ("dashboard", "Dashboard", "go-home-symbolic", P.DashboardPage),
    ("services", "Services", "applications-system-symbolic", P.ServicesPage),
    ("sites", "Sites", "web-browser-symbolic", P.SitesPage),
    ("databases", "Databases", "drive-harddisk-symbolic", P.DatabasesPage),
    ("node", "Node", "application-x-addon-symbolic", P.NodePage),
    ("python", "Python", "application-x-executable-symbolic", P.PythonPage),
    ("logs", "Logs", "text-x-generic-symbolic", P.LogsPage),
    ("settings", "Settings", "preferences-system-symbolic", P.SettingsPage),
]


class MainWindow(Adw.ApplicationWindow):
    def __init__(self, app) -> None:
        super().__init__(application=app, title="OmniServ", default_width=1080, default_height=720)
        self.engine = app.engine
        self.app_version = __version__
        self.last_data: dict = {}
        self.pages: dict = {}
        self.applog: list = []   # recent verb activity, shown in the Dashboard activity log

        self.toast_overlay = Adw.ToastOverlay()
        split = Adw.OverlaySplitView()
        self.split = split
        self.toast_overlay.set_child(split)
        self.set_content(self.toast_overlay)

        # ── sidebar: app icon + name at the top, nav in the middle, Settings pinned
        #    at the bottom (parity with the Windows NavigationView / macOS source list) ──
        sidebar_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, css_classes=["bh-sidebar"])

        brand = Gtk.Box(spacing=10, margin_top=14, margin_bottom=14, margin_start=14, margin_end=12)
        app_icon = Gtk.Image.new_from_icon_name("com.emon.omniserv")
        app_icon.set_pixel_size(28)
        brand.append(app_icon)
        name_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, valign=Gtk.Align.CENTER, hexpand=True)
        name_box.append(Gtk.Label(label="OmniServ", xalign=0, css_classes=["bh-brand"]))
        name_box.append(Gtk.Label(label="Local server", xalign=0, css_classes=["dim-label", "caption"]))
        brand.append(name_box)
        self.spinner = Gtk.Spinner(valign=Gtk.Align.CENTER)
        brand.append(self.spinner)
        sidebar_box.append(brand)
        sidebar_box.append(Gtk.Separator())

        # nav items (everything except Settings)
        self.sidebar_list = Gtk.ListBox(css_classes=["navigation-sidebar"])
        self.sidebar_list.connect("row-selected", self._on_nav)
        for key, label, icon, _cls in NAV:
            if key == "settings":
                continue
            self.sidebar_list.append(self._nav_row(key, label, icon))
        sb_scroll = Gtk.ScrolledWindow(vexpand=True)
        sb_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        sb_scroll.set_child(self.sidebar_list)
        sidebar_box.append(sb_scroll)

        # Settings pinned to the bottom
        sidebar_box.append(Gtk.Separator())
        self.settings_list = Gtk.ListBox(css_classes=["navigation-sidebar"])
        self.settings_list.connect("row-selected", self._on_nav)
        self.settings_list.append(self._nav_row("settings", "Settings", "preferences-system-symbolic"))
        sidebar_box.append(self.settings_list)

        split.set_sidebar(sidebar_box)
        split.set_min_sidebar_width(220)
        split.set_max_sidebar_width(260)

        # ── content ──
        content_tv = Adw.ToolbarView()
        self.content_header = Adw.HeaderBar()
        self.sidebar_toggle = Gtk.ToggleButton(icon_name="sidebar-show-symbolic",
                                                tooltip_text="Toggle sidebar", active=True)
        self.sidebar_toggle.connect("toggled",
                                    lambda b: self.split.set_show_sidebar(b.get_active()))
        self.content_header.pack_start(self.sidebar_toggle)
        self.content_title = Adw.WindowTitle(title="Dashboard", subtitle="")
        self.content_header.set_title_widget(self.content_title)
        refresh_btn = Gtk.Button(icon_name="view-refresh-symbolic", tooltip_text="Refresh")
        refresh_btn.connect("clicked", lambda *_: self.refresh())
        self.content_header.pack_end(refresh_btn)
        content_tv.add_top_bar(self.content_header)

        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)
        for key, _label, _icon, cls in NAV:
            page = cls(self)
            self.pages[key] = page
            self.stack.add_named(page, key)
        content_tv.set_content(self.stack)
        split.set_content(content_tv)
        # keep the toggle button in sync when the split collapses/expands on its own
        split.connect("notify::show-sidebar",
                      lambda s, _p: self.sidebar_toggle.set_active(s.get_show_sidebar()))

        self.sidebar_list.select_row(self.sidebar_list.get_row_at_index(0))
        self.refresh()
        GLib.timeout_add_seconds(4, self._tick)
        # auto update-check shortly after launch (throttled + gated by the toggle), then daily
        GLib.timeout_add_seconds(3, lambda: (self.check_updates(False), False)[1])
        GLib.timeout_add_seconds(24 * 3600, lambda: (self.check_updates(False), True)[1])

    # ── navigation ──
    def _nav_row(self, key: str, label: str, icon: str) -> Gtk.ListBoxRow:
        row = Gtk.ListBoxRow()
        b = Gtk.Box(spacing=12, margin_top=8, margin_bottom=8, margin_start=8, margin_end=8)
        b.append(Gtk.Image.new_from_icon_name(icon))
        b.append(Gtk.Label(label=label, xalign=0))
        row.set_child(b)
        row.nav_key = key
        return row

    def _on_nav(self, listbox, row) -> None:
        if not row:
            return
        # nav and Settings are two separate lists — clear the other so only one row
        # stays highlighted at a time.
        other = self.settings_list if listbox is self.sidebar_list else self.sidebar_list
        if other.get_selected_row() is not None:
            other.unselect_all()
        key = row.nav_key
        self.stack.set_visible_child_name(key)
        label = next(l for k, l, _i, _c in NAV if k == key)
        self.content_title.set_title(label)
        page = self.pages[key]
        if hasattr(page, "refresh") and self.last_data:
            page.refresh(self.last_data)

    # ── api refresh loop ──
    def _tick(self) -> bool:
        self.refresh()
        return True

    def refresh(self) -> None:
        def worker():
            data = self.engine.api()
            GLib.idle_add(self._apply, data)
        threading.Thread(target=worker, daemon=True).start()

    def _apply(self, data: dict) -> bool:
        if data:
            self.last_data = data
        key = self.stack.get_visible_child_name()
        page = self.pages.get(key)
        if page and hasattr(page, "refresh"):
            try:
                page.refresh(self.last_data)
            except Exception as e:  # noqa: BLE001
                print("refresh error:", e)
        return False

    # ── verb runner ──
    def run_verb(self, args, msg, refresh=True, then=None, env=None, force_root=False) -> None:
        if msg:
            self.toast(msg)
            self._applog(msg)
        self.spinner.start()

        def done(rc, out):
            self.spinner.stop()
            if rc != 0:
                err = D._first_line(out) or f"{' '.join(args)} failed"
                self.toast(err)
                self._applog(f"✗ {err}")
            elif msg:
                self.toast(msg.replace("…", " — done"))
                self._applog(msg.replace("…", " — done"))
            if rc == 0 and then:   # chain a follow-up verb on success (e.g. install → use)
                self.run_verb(then[0], then[1], refresh=refresh)
            elif refresh:
                self.refresh()

        self.engine.run_async(list(args), done, env=env, force_root=force_root)

    def run_progress(self, args, title, working, ok_msg, refresh=True) -> None:
        D.run_progress(self, args, title, working, ok_msg, refresh=refresh)

    def _applog(self, line: str) -> None:
        self.applog.append(line)
        del self.applog[:-200]

    def toast(self, text: str) -> None:
        self.toast_overlay.add_toast(Adw.Toast(title=text, timeout=3))

    # ── update & about ──
    def check_updates(self, force: bool = False) -> None:
        D.check_updates(self, force=force)

    def about(self) -> None:
        D.about_dialog(self)

    # ── dialog facades (delegating to dialogs module) ──
    def confirm(self, title, body, on_ok) -> None:
        D.confirm(self, title, body, on_ok)

    def choose(self, title, body, options, on_pick) -> None:
        D.choose(self, title, body, options, on_pick)

    def add_site_dialog(self, default_type="wordpress") -> None:
        D.add_site_dialog(self, default_type=default_type)

    def create_db_dialog(self) -> None:
        D.create_db_dialog(self)

    def db_root_dialog(self) -> None:
        D.db_root_dialog(self)

    def db_password_dialog(self, name) -> None:
        D.db_password_dialog(self, name)

    def db_drop(self, name, engine="mysql") -> None:
        D.db_drop(self, name, engine=engine)

    def _copy(self, text) -> None:
        D.copy_text(self, text)

    def site_share(self, name) -> None:
        D.site_share(self, name)

    # ── GUI prefs (delegating to prefs module) ──
    def cfg_int(self, key, default) -> int:
        return prefs.cfg_int(key, default)

    def cfg_bool(self, key, default) -> bool:
        return prefs.cfg_bool(key, default)

    def set_cfg(self, key, value) -> None:
        prefs.set_cfg(key, value)
