"""Settings pane: comprehensive server topology, site defaults, startup & system integration,
theme & appearance preferences, page sizes, diagnostics doctor, and About dialog.
"""
from __future__ import annotations

import os
import threading

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, Gtk  # noqa: E402

from ..widgets import PAGE_SIZES, page_size_to_int, pill
from ._shared import PHP_KEYS, _open, _open_text_editor


class SettingsPage(Gtk.Box):
    def __init__(self, win) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.win = win
        self._syncing = False   # True while refresh() updates widgets to prevent firing save actions
        self._last_tld = "test"
        self._last_http = 80
        self._last_https = 443
        self._last_sites_root = os.path.expanduser("~/OmniServ/www")
        self._last_default_php = "8.4"
        self._last_default_web = "nginx"
        self._installed_phps: list[str] = []

        scroller = Gtk.ScrolledWindow(vexpand=True, hexpand=True)
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.append(scroller)

        outer_box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=18,
            margin_top=18,
            margin_bottom=24,
            margin_start=18,
            margin_end=18,
        )
        scroller.set_child(outer_box)

        # ── 1. In-Page Header ──
        head_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        title_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, hexpand=True)
        title_box.append(Gtk.Label(label="Settings", xalign=0, css_classes=["title-1"]))
        title_box.append(
            Gtk.Label(
                label="Configure server topology, ports, environment defaults, startup, and preferences",
                xalign=0,
                css_classes=["dim-label"],
            )
        )
        head_box.append(title_box)

        # Version Pill on top right
        ver_box = Gtk.Box(valign=Gtk.Align.CENTER)
        self.ver_pill = pill(f"v{self.win.app_version}", "bh-pill-blue")
        ver_box.append(self.ver_pill)
        head_box.append(ver_box)
        outer_box.append(head_box)

        # ── 2. Quick Server Overview Banner ──
        self.banner = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=12,
            css_classes=["bh-settings-banner"],
        )
        banner_top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        banner_icon = Gtk.Image.new_from_icon_name("preferences-system-symbolic")
        banner_icon.set_pixel_size(20)
        banner_top.append(banner_icon)
        banner_top.append(
            Gtk.Label(
                label="Server Environment Overview",
                xalign=0,
                hexpand=True,
                css_classes=["bh-brand"],
            )
        )
        self.banner.append(banner_top)

        # Summary Chips Flow
        chips_flow = Gtk.FlowBox(
            selection_mode=Gtk.SelectionMode.NONE,
            max_children_per_line=6,
            min_children_per_line=2,
            row_spacing=8,
            column_spacing=8,
        )

        self.chip_tld_val = Gtk.Label(label=".test", css_classes=["bh-settings-chip-val"])
        chips_flow.append(self._make_chip("Domain TLD", self.chip_tld_val))

        self.chip_ports_val = Gtk.Label(label="80 / 443", css_classes=["bh-settings-chip-val"])
        chips_flow.append(self._make_chip("Ports (HTTP/S)", self.chip_ports_val))

        self.chip_php_val = Gtk.Label(label="PHP 8.4", css_classes=["bh-settings-chip-val"])
        chips_flow.append(self._make_chip("Default PHP", self.chip_php_val))

        self.chip_web_val = Gtk.Label(label="nginx", css_classes=["bh-settings-chip-val"])
        chips_flow.append(self._make_chip("Default Web", self.chip_web_val))

        self.chip_helper_val = Gtk.Label(label="Active", css_classes=["bh-settings-chip-val"])
        chips_flow.append(self._make_chip("Sudo Helper", self.chip_helper_val))

        self.banner.append(chips_flow)

        # Quick directory shortcut buttons
        shortcuts_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)

        b_home = Gtk.Button(label="Open OmniServ Data (~/.omniserv)", icon_name="folder-symbolic", css_classes=["flat"])
        b_home.connect("clicked", lambda *_: _open(os.path.expanduser("~/.omniserv")))
        shortcuts_row.append(b_home)

        b_sites = Gtk.Button(label="Open Sites Directory", icon_name="folder-remote-symbolic", css_classes=["flat"])
        b_sites.connect("clicked", lambda *_: _open(self._last_sites_root))
        shortcuts_row.append(b_sites)

        b_logs = Gtk.Button(label="View Logs", icon_name="text-x-generic-symbolic", css_classes=["flat"])
        b_logs.connect("clicked", lambda *_: _open(os.path.expanduser("~/.omniserv/logs")))
        shortcuts_row.append(b_logs)

        self.banner.append(shortcuts_row)
        outer_box.append(self.banner)

        # ── 3. Libadwaita Preferences Page ──
        self.pref_page = Adw.PreferencesPage()
        outer_box.append(self.pref_page)

        self._build_topology_group()
        self._build_site_defaults_group()
        self._build_startup_system_group()
        self._build_appearance_sizes_group()
        self._build_updates_group()
        self._build_diagnostics_tools_group()
        self._build_about_group()

    def _make_chip(self, label: str, val_widget: Gtk.Widget) -> Gtk.Widget:
        b = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, css_classes=["bh-settings-chip"])
        b.append(Gtk.Label(label=label, xalign=0, css_classes=["bh-settings-chip-lbl"]))
        b.append(val_widget)
        return b

    # ── Group 1: Domains and Network Topology ──
    def _build_topology_group(self) -> None:
        g = Adw.PreferencesGroup(
            title="Domains and Network Topology",
            description="Configure the local top-level domain and reverse proxy server ports",
        )

        self.tld_row = Adw.EntryRow(title="Local Domain TLD")
        self.tld_row.set_text("test")
        self.tld_row.connect("changed", self._check_topology_dirty)
        g.add(self.tld_row)

        self.http_port_row = Adw.SpinRow.new_with_range(1, 65535, 1)
        self.http_port_row.set_title("HTTP Port")
        self.http_port_row.set_subtitle("Default: 80 (standard HTTP web server port)")
        self.http_port_row.set_value(80)
        self.http_port_row.connect("notify::value", self._check_topology_dirty)
        g.add(self.http_port_row)

        self.https_port_row = Adw.SpinRow.new_with_range(1, 65535, 1)
        self.https_port_row.set_title("HTTPS Port")
        self.https_port_row.set_subtitle("Default: 443 (standard HTTPS SSL port)")
        self.https_port_row.set_value(443)
        self.https_port_row.connect("notify::value", self._check_topology_dirty)
        g.add(self.https_port_row)

        # Save & Revert bar
        self.topo_save_row = Adw.ActionRow(
            title="Apply Topology Changes",
            subtitle="Ports below 1024 (80/443) require administrator privilege. Saving re-renders virtual hosts and reloads the web server.",
        )
        self.topo_save_btn = Gtk.Button(
            label="Save Changes",
            css_classes=["suggested-action"],
            valign=Gtk.Align.CENTER,
            sensitive=False,
        )
        self.topo_save_btn.connect("clicked", self._save_topology)
        self.topo_revert_btn = Gtk.Button(
            label="Revert",
            valign=Gtk.Align.CENTER,
            sensitive=False,
        )
        self.topo_revert_btn.connect("clicked", self._revert_topology)

        action_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        action_box.append(self.topo_revert_btn)
        action_box.append(self.topo_save_btn)
        self.topo_save_row.add_suffix(action_box)
        g.add(self.topo_save_row)

        self.pref_page.add(g)

    def _check_topology_dirty(self, *_) -> None:
        if self._syncing:
            return
        tld_val = self.tld_row.get_text().strip().lstrip(".")
        http_val = int(self.http_port_row.get_value())
        https_val = int(self.https_port_row.get_value())

        dirty = (
            tld_val != self._last_tld
            or http_val != self._last_http
            or https_val != self._last_https
        )
        self.topo_save_btn.set_sensitive(dirty)
        self.topo_revert_btn.set_sensitive(dirty)

    def _save_topology(self, *_) -> None:
        new_tld = self.tld_row.get_text().strip().lstrip(".")
        new_http = int(self.http_port_row.get_value())
        new_https = int(self.https_port_row.get_value())

        if not new_tld:
            self.win.toast("TLD cannot be empty")
            return

        self.topo_save_btn.set_sensitive(False)
        self.topo_revert_btn.set_sensitive(False)

        def worker():
            if new_tld != self._last_tld:
                self.win.engine.run("config", "set", "tld", new_tld)
            if new_http != self._last_http:
                self.win.engine.run("config", "set", "http_port", str(new_http))
            if new_https != self._last_https:
                self.win.engine.run("config", "set", "https_port", str(new_https))
            GLib.idle_add(lambda: (self.win.toast("Topology configuration updated"), self.win.refresh(), False)[2])

        threading.Thread(target=worker, daemon=True).start()

    def _revert_topology(self, *_) -> None:
        self._syncing = True
        self.tld_row.set_text(self._last_tld)
        self.http_port_row.set_value(self._last_http)
        self.https_port_row.set_value(self._last_https)
        self._syncing = False
        self.topo_save_btn.set_sensitive(False)
        self.topo_revert_btn.set_sensitive(False)

    # ── Group 2: Defaults for New Sites ──
    def _build_site_defaults_group(self) -> None:
        g = Adw.PreferencesGroup(
            title="Defaults for New Sites",
            description="Default runtime stack and directory applied when creating new sites",
        )

        # Default PHP Version
        php_options = [k.replace("php@", "") for k in PHP_KEYS]
        self.default_php_row = Adw.ComboRow(
            title="Default PHP Version",
            subtitle="PHP version assigned to newly added WordPress and PHP projects",
            model=Gtk.StringList.new(php_options),
        )
        self.default_php_row.connect("notify::selected", self._on_php_selected)
        g.add(self.default_php_row)

        # Default Web Server
        self.default_web_row = Adw.ComboRow(
            title="Default Web Server",
            subtitle="Web server backend for new sites (Nginx direct FastCGI vs Apache reverse proxy)",
            model=Gtk.StringList.new(["nginx (Direct PHP)", "Apache (Reverse Proxy)", "OpenLiteSpeed"]),
        )
        self.default_web_row.connect("notify::selected", self._on_web_selected)
        g.add(self.default_web_row)

        # Default Sites Root Directory
        self.sites_root_row = Adw.ActionRow(
            title="Sites Root Directory",
            subtitle=self._last_sites_root,
        )
        browse_btn = Gtk.Button(label="Browse…", valign=Gtk.Align.CENTER)
        browse_btn.connect("clicked", self._browse_sites_root)
        open_btn = Gtk.Button(icon_name="folder-open-symbolic", tooltip_text="Open in File Manager", valign=Gtk.Align.CENTER)
        open_btn.connect("clicked", lambda *_: _open(self._last_sites_root))

        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        btn_box.append(open_btn)
        btn_box.append(browse_btn)
        self.sites_root_row.add_suffix(btn_box)
        g.add(self.sites_root_row)

        self.pref_page.add(g)

    def _on_php_selected(self, row, _p) -> None:
        if self._syncing:
            return
        options = self._installed_phps or [k.replace("php@", "") for k in PHP_KEYS]
        idx = row.get_selected()
        if 0 <= idx < len(options):
            chosen = options[idx]
            self.win.engine.run("config", "set", "default_php", chosen)
            self.win.toast(f"Default PHP set to {chosen}")

    def _on_web_selected(self, row, _p) -> None:
        if self._syncing:
            return
        idx = row.get_selected()
        mapping = ["nginx", "apache", "ols"]
        if 0 <= idx < len(mapping):
            chosen = mapping[idx]
            self.win.engine.run("config", "set", "default_web", chosen)
            self.win.toast(f"Default web server set to {chosen}")

    def _browse_sites_root(self, *_) -> None:
        def on_pick(dialog, result):
            try:
                f = dialog.select_folder_finish(result)
                if f:
                    path = f.get_path()
                    self._last_sites_root = path
                    self.sites_root_row.set_subtitle(path)
                    self.win.engine.run("config", "set", "sites_root", path)
                    self.win.toast(f"Sites root set to {path}")
                    self.win.refresh()
            except Exception:
                pass

        dlg = Gtk.FileDialog()
        dlg.set_title("Select Default Sites Directory")
        if os.path.isdir(self._last_sites_root):
            dlg.set_initial_folder(Gio.File.new_for_path(self._last_sites_root))
        dlg.select_folder(self.win, None, on_pick)

    # ── Group 3: Startup and System Integration ──
    def _build_startup_system_group(self) -> None:
        g = Adw.PreferencesGroup(
            title="Startup and System Integration",
            description="Manage background daemons, login autostart, and privileged execution",
        )

        # Login Autostart
        self.autostart = Adw.SwitchRow(
            title="Start OmniServ at login",
            subtitle="Starts background services at boot and launches the tray indicator on user login",
        )
        self.autostart.connect("notify::active", self._toggle_autostart)
        g.add(self.autostart)

        # Start services on app launch
        self.start_on_launch = Adw.SwitchRow(
            title="Start services automatically on app launch",
            subtitle="Automatically boots all configured daemons when opening the OmniServ application",
            active=False,
        )
        self.start_on_launch.connect("notify::active", self._toggle_start_on_launch)
        g.add(self.start_on_launch)

        # Minimize to Tray
        self.tray_close = Adw.SwitchRow(
            title="Minimize to system tray on window close",
            subtitle="Keep background services running and minimize to tray instead of quitting",
            active=self.win.cfg_bool("minimize_to_tray", True),
        )
        self.tray_close.connect("notify::active", lambda r, _p: self.win.set_cfg("minimize_to_tray", r.get_active()))
        g.add(self.tray_close)

        # Sudoers Helper
        self.helper_row = Adw.ActionRow(
            title="Password-less Service Control (Sudoers Helper)",
            subtitle="Installs /etc/sudoers.d/omniserv rule so starting/stopping Nginx on :80/:443 never prompts for a password",
        )
        self.helper_badge = pill("Checking…", "bh-pill-off")
        self.helper_btn = Gtk.Button(label="Configure", valign=Gtk.Align.CENTER)
        self.helper_btn.connect("clicked", self._toggle_helper)

        h_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        h_box.append(self.helper_badge)
        h_box.append(self.helper_btn)
        self.helper_row.add_suffix(h_box)
        g.add(self.helper_row)

        self.pref_page.add(g)

    def _toggle_autostart(self, row, _p) -> None:
        if self._syncing:
            return
        self.win.run_verb(["loginitem", "enable" if row.get_active() else "disable"], None, refresh=False)

    def _toggle_start_on_launch(self, row, _p) -> None:
        if self._syncing:
            return
        self.win.engine.run("config", "set", "autostart", "true" if row.get_active() else "false")
        self.win.toast("Autostart setting updated")

    def _toggle_helper(self, *_) -> None:
        is_installed = getattr(self, "_helper_installed", False)
        if is_installed:
            self.win.confirm(
                "Remove Sudoers Helper?",
                "Starting and stopping web servers on privileged ports will require entering your administrator password.",
                lambda: self.win.run_verb(["helper", "uninstall"], "Removing privileged helper…")
            )
        else:
            self.win.run_verb(["helper", "install"], "Installing privileged helper…")

    # ── Group 4: Appearance and List Sizes ──
    def _build_appearance_sizes_group(self) -> None:
        g = Adw.PreferencesGroup(
            title="Appearance and UI Preferences",
            description="Customize color theme and default rows per page for lists",
        )

        # Theme / Color Scheme
        cur_theme = self.win.cfg_str("color_scheme", "system")
        theme_map = {"system": 0, "dark": 1, "light": 2}
        self.theme_row = Adw.ComboRow(
            title="Color Scheme / Theme",
            subtitle="Choose between system default, dark mode, or light mode",
            model=Gtk.StringList.new(["Follow System", "Dark Mode", "Light Mode"]),
        )
        self.theme_row.set_selected(theme_map.get(cur_theme, 0))
        self.theme_row.connect("notify::selected", self._on_theme_selected)
        g.add(self.theme_row)

        # Page Sizes
        self.sizes = {}
        for key, label, dflt in (
            ("dashboard_page_size", "Dashboard Websites per page", 5),
            ("sites_page_size", "Sites List per page", 15),
            ("databases_page_size", "Databases List per page", 15),
            ("apps_page_size", "Node and Python Apps per page", 15),
        ):
            r = Adw.ComboRow(
                title=label,
                subtitle="Default page size (individual views can override with their 'Show' dropdown)",
                model=Gtk.StringList.new(PAGE_SIZES),
            )
            cur = self.win.cfg_int(key, dflt)
            try:
                r.set_selected(PAGE_SIZES.index("All" if cur >= 10 ** 8 else str(cur)))
            except ValueError:
                r.set_selected(1)
            r.connect(
                "notify::selected",
                lambda row, _p, k=key: self.win.set_cfg(k, page_size_to_int(PAGE_SIZES[row.get_selected()])),
            )
            self.sizes[key] = r
            g.add(r)

        self.pref_page.add(g)

    def _on_theme_selected(self, row, _p) -> None:
        idx = row.get_selected()
        mapping = {0: "system", 1: "dark", 2: "light"}
        chosen = mapping.get(idx, "system")
        self.win.set_cfg("color_scheme", chosen)

        sm = Adw.StyleManager.get_default()
        if chosen == "dark":
            sm.set_color_scheme(Adw.ColorScheme.FORCE_DARK)
        elif chosen == "light":
            sm.set_color_scheme(Adw.ColorScheme.FORCE_LIGHT)
        else:
            sm.set_color_scheme(Adw.ColorScheme.DEFAULT)
        self.win.toast(f"Theme set to {['System Default', 'Dark Mode', 'Light Mode'][idx]}")

    # ── Group 5: Application Updates ──
    def _build_updates_group(self) -> None:
        g = Adw.PreferencesGroup(
            title="Application Updates",
            description="Manage automatic update checks and upgrade OmniServ packages",
        )

        self.autoupdate = Adw.SwitchRow(
            title="Check for updates automatically",
            subtitle="Periodically check GitHub releases in the background (at most once every 30 minutes)",
            active=self.win.cfg_bool("auto_update", True),
        )
        self.autoupdate.connect(
            "notify::active",
            lambda r, _p: self.win.set_cfg("auto_update", r.get_active()),
        )
        g.add(self.autoupdate)

        self.update_row = Adw.ActionRow(
            title=f"OmniServ for Linux · v{self.win.app_version}",
            subtitle="Release channel: Stable (.deb / GitHub Releases)",
        )
        check_btn = Gtk.Button(label="Check for Updates", icon_name="view-refresh-symbolic", valign=Gtk.Align.CENTER)
        check_btn.connect("clicked", lambda *_: self.win.check_updates(force=True))
        self.update_row.add_suffix(check_btn)
        g.add(self.update_row)

        self.pref_page.add(g)

    # ── Group 6: Diagnostics, Maintenance and Tools ──
    def _build_diagnostics_tools_group(self) -> None:
        g = Adw.PreferencesGroup(
            title="Diagnostics and Maintenance",
            description="System health check, configuration files, and virtual host management",
        )

        # System Doctor
        doc_row = Adw.ActionRow(
            title="System Doctor and Health Diagnostics",
            subtitle="Inspect Homebrew, system paths, PHP socket directories, port availability, and dependencies",
        )

        doc_btn = Gtk.Button(label="Run Doctor", icon_name="emblem-default-symbolic", valign=Gtk.Align.CENTER)
        doc_btn.connect("clicked", lambda *_: self.win.doctor())
        doc_row.add_suffix(doc_btn)
        g.add(doc_row)

        # Rebuild Virtual Hosts
        regen_row = Adw.ActionRow(
            title="Rebuild All Virtual Hosts",
            subtitle="Regenerates Nginx and Apache configuration files for all active websites and reloads web servers",
        )
        regen_btn = Gtk.Button(label="Rebuild", icon_name="document-revert-symbolic", valign=Gtk.Align.CENTER)
        def on_regen(*_):
            tld = self.tld_row.get_text().strip().lstrip(".") or "test"
            self.win.run_verb(["config", "set", "tld", tld], "Rebuilding all site virtual hosts…")
        regen_btn.connect("clicked", on_regen)
        regen_row.add_suffix(regen_btn)
        g.add(regen_row)

        # Config File Shortcut
        conf_path = os.path.expanduser("~/.omniserv/config/omniserv.json")
        conf_row = Adw.ActionRow(
            title="OmniServ Configuration File",
            subtitle=conf_path,
        )
        b_edit_conf = Gtk.Button(label="Open in Editor", icon_name="text-editor-symbolic", valign=Gtk.Align.CENTER)
        b_edit_conf.connect("clicked", lambda *_: _open_text_editor(conf_path))
        conf_row.add_suffix(b_edit_conf)
        g.add(conf_row)

        self.pref_page.add(g)

    # ── Group 7: About OmniServ ──
    def _build_about_group(self) -> None:
        g = Adw.PreferencesGroup(title="About OmniServ")

        about_row = Adw.ActionRow(
            title=f"OmniServ for Linux · v{self.win.app_version}",
            subtitle="Developed by Emon Khan (emon.bd) · Open source under the MIT License",
            activatable=True,
        )
        about_row.connect("activated", lambda *_: self.win.about())

        b_web = Gtk.Button(icon_name="web-browser-symbolic", tooltip_text="Website (emon.bd)", valign=Gtk.Align.CENTER)
        b_web.connect("clicked", lambda *_: _open("https://emon.bd"))

        b_gh = Gtk.Button(icon_name="software-update-available-symbolic", tooltip_text="GitHub Repository", valign=Gtk.Align.CENTER)
        b_gh.connect("clicked", lambda *_: _open("https://github.com/plusemon/OmniServ"))

        b_dialog = Gtk.Button(label="About OmniServ", icon_name="help-about-symbolic", valign=Gtk.Align.CENTER)
        b_dialog.connect("clicked", lambda *_: self.win.about())

        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        btn_box.append(b_web)
        btn_box.append(b_gh)
        btn_box.append(b_dialog)
        about_row.add_suffix(btn_box)
        g.add(about_row)

        self.pref_page.add(g)

    # ── Refresh Hook (called by MainWindow on API ticks) ──
    def refresh(self, data: dict) -> None:
        self._syncing = True
        try:
            cfg = data.get("config", {})
            tld = cfg.get("tld", "test")
            http = int(cfg.get("http_port", 80))
            https = int(cfg.get("https_port", 443))
            dphp = cfg.get("default_php", "8.4")
            dweb = cfg.get("default_web", "nginx")
            sroot = cfg.get("sites_root", os.path.expanduser("~/OmniServ/www"))
            autostart_cfg = bool(cfg.get("autostart", False))

            self._last_tld = tld
            self._last_http = http
            self._last_https = https
            self._last_sites_root = sroot
            self._last_default_php = dphp
            self._last_default_web = dweb

            # Update overview chips
            self.chip_tld_val.set_label(f".{tld}")
            self.chip_ports_val.set_label(f"{http} / {https}")
            self.chip_php_val.set_label(f"PHP {dphp.replace('php@', '')}")
            self.chip_web_val.set_label(dweb)

            is_helper = bool(data.get("helper", False))
            self._helper_installed = is_helper
            self.chip_helper_val.set_label("Active" if is_helper else "Not Set")

            # Helper status badge & button text
            if is_helper:
                self.helper_badge.set_label("● Active")
                self.helper_badge.set_css_classes(["bh-pill", "bh-pill-on"])
                self.helper_btn.set_label("Remove")
                self.helper_btn.set_css_classes(["destructive-action"])
            else:
                self.helper_badge.set_label("● Not Configured")
                self.helper_badge.set_css_classes(["bh-pill", "bh-pill-off"])
                self.helper_btn.set_label("Enable")
                self.helper_btn.set_css_classes(["suggested-action"])

            # Form fields
            if not self.topo_save_btn.get_sensitive():
                self.tld_row.set_text(tld)
                self.http_port_row.set_value(http)
                self.https_port_row.set_value(https)

            self.sites_root_row.set_subtitle(sroot)

            # Discover installed PHP versions
            installed = [
                s["key"].replace("php@", "")
                for s in data.get("services", [])
                if s.get("role") == "php" and s.get("installed")
            ]
            php_choices = installed or [k.replace("php@", "") for k in PHP_KEYS]
            if php_choices != self._installed_phps:
                self._installed_phps = php_choices
                self.default_php_row.set_model(Gtk.StringList.new(php_choices))

            clean_dphp = dphp.replace("php@", "")
            if clean_dphp in php_choices:
                self.default_php_row.set_selected(php_choices.index(clean_dphp))

            # Default Web
            web_map = {"nginx": 0, "apache": 1, "ols": 2, "openlitespeed": 2}
            self.default_web_row.set_selected(web_map.get(dweb, 0))

            # Login autostart & launch autostart
            self.autostart.set_active(bool(data.get("loginitem")))
            self.start_on_launch.set_active(autostart_cfg)

        except Exception as e:
            print("SettingsPage refresh error:", e)
        finally:
            self._syncing = False

