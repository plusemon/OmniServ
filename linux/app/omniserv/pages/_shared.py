"""Shared helpers, widgets, and dialogs used across the OmniServ UI pages."""
from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
from typing import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, Gtk, Pango  # noqa: E402

from ..widgets import pill, status_dot

# The CPU sparkline uses a Cairo draw callback, which needs the cairo↔Python foreign-struct
# converter (the python3-gi-cairo package). If it's missing, drawing throws in the marshaller
# *before* our code runs — so detect it up front and skip the sparkline rather than flood errors.
try:
    gi.require_foreign("cairo")
    _HAVE_CAIRO = True
except Exception:
    _HAVE_CAIRO = False

PHP_KEYS = ["php@8.6", "php@8.5", "php@8.4", "php@8.3", "php@8.2", "php@8.1", "php@8.0", "php@7.4"]
SERVICE_GROUPS = [
    ("PHP", "php"),
    ("Web servers", "web"),
    ("Databases", "db"),
    ("Cache", "cache"),
    ("DNS / TLS / Mail", "dns tls mail"),
    ("Runtimes", "node python"),
]
ROLE_LABEL = {
    "php": "PHP", "web": "Web", "db": "Database", "cache": "Cache",
    "dns": "DNS", "tls": "TLS", "mail": "Mail", "node": "Node", "python": "Python",
}


def clean_version(s: str) -> str:
    """The engine's version probe can truncate ('PHP 8.4.22 (fpm-fcgi) (built: …'); keep
    just the meaningful 'Name X.Y.Z'."""
    if not s:
        return ""
    m = re.search(r"(\d+\.\d+(?:\.\d+)?)", s)
    return m.group(1) if m else s.strip()[:24]


def _open(path_or_url: str) -> None:
    try:
        Gio.AppInfo.launch_default_for_uri(
            path_or_url if "://" in path_or_url else GLib.filename_to_uri(path_or_url, None),
            None,
        )
    except Exception:
        subprocess.Popen(["xdg-open", path_or_url])


def _open_editor(folder: str) -> None:
    for ed in ("code", "codium", "cursor", "subl", "gnome-text-editor", "gedit"):
        if shutil.which(ed):
            subprocess.Popen([ed, folder])
            return
    _open(folder)


def _open_terminal(folder: str) -> None:
    for term, args in (
        ("gnome-terminal", ["--working-directory", folder]),
        ("konsole", ["--workdir", folder]),
        ("xfce4-terminal", ["--working-directory", folder]),
        ("xterm", ["-e", "bash", "-c", f"cd {shlex.quote(folder)} && exec bash"]),
    ):
        if shutil.which(term):
            subprocess.Popen([term, *args])
            return


# ── shared site row (used by both the Sites pane and the Dashboard websites panel) ──
TOOL_NAMES = {"phpmyadmin", "adminer", "mailpit"}


def is_tool(name: str) -> bool:
    return name in TOOL_NAMES


def site_match(s: dict, q: str) -> bool:
    q = q.lower()
    return q in s["name"].lower() or q in s.get("php", "").lower()


def _is_ols(s: dict) -> bool:
    """OLS-backed sites need root for their config resync + reload ($SUDO cp into
    /usr/local/lsws/conf + systemctl) — normally-unprivileged site verbs (php/subdomain)
    must run privileged for them, or the change silently never reaches OLS."""
    return s.get("server") in ("ols", "openlitespeed")


def site_change_php(win, s: dict) -> None:
    installed = [x["key"].replace("php@", "") for x in win.last_data.get("services", [])
                 if x["role"] == "php" and x["installed"]]
    win.choose("Change PHP version", f"Pick a PHP version for {s['name']}", installed,
               lambda v: win.run_verb(["site", "php", s["name"], v], f"Switching {s['name']} → PHP {v}…",
                                      force_root=_is_ols(s)))


# Web servers a site can be switched to, in menu order. Only the ones the site is NOT
# currently using are shown (see _site_menu) — you never see "Switch to X" for the X you're on.
_WEB_SERVERS = [("nginx", "Switch to nginx"),
                ("apache", "Switch to Apache"),
                ("ols", "Switch to OpenLiteSpeed")]


def site_change_root(win, s: dict) -> None:
    def on_pick(dialog, result):
        try:
            f = dialog.select_folder_finish(result)
            if f:
                path = f.get_path()
                win.run_verb(["site", "root", s["name"], path], f"Changing root for {s['name']} → {path}…")
        except Exception:
            pass

    dlg = Gtk.FileDialog()
    dlg.set_title(f"Select new root directory for {s['name']}")
    if s.get("root") and os.path.isdir(s["root"]):
        dlg.set_initial_folder(Gio.File.new_for_path(s["root"]))
    dlg.select_folder(win, None, on_pick)


class SiteConfigDialog(Adw.Window):
    """aaPanel-style site configuration dialog.
    Two-pane layout:
      Left pane: Navigation list with tabs (Domain Manager, Directory, Config, SSL, PHP version, Web Server, Share / Tunnel, Delete Site)
      Right pane: Stack of configuration panels matching the selected tab.
    """
    SECTIONS = [
        ("domain", "Domain Manager", "network-server-symbolic"),
        ("root", "Directory", "folder-symbolic"),
        ("config", "Config", "text-editor-symbolic"),
        ("ssl", "SSL", "security-high-symbolic"),
        ("php", "PHP version", "application-x-php-symbolic"),
        ("server", "Web Server", "network-server-symbolic"),
        ("share", "Share / Tunnel", "network-wireless-symbolic"),
        ("delete", "Delete Site", "user-trash-symbolic"),
    ]

    def __init__(self, win, s: dict) -> None:
        super().__init__(
            transient_for=win,
            modal=True,
            title=f"Site modification [{s.get('domain', s.get('name'))}]",
            default_width=780,
            default_height=530,
        )
        self.win = win
        self.site_name = s["name"]
        self._initial_site = dict(s)
        self._current_key = "domain"

        tv = Adw.ToolbarView()
        self.set_content(tv)

        # Header Bar
        hb = Adw.HeaderBar()
        site = self._get_site()
        self.title_widget = Adw.WindowTitle(
            title=f"Site modification [{site.get('domain', self.site_name)}]",
            subtitle=f"{site.get('php', '')} · {site.get('server', 'nginx')} · {'HTTPS' if site.get('secure') else 'HTTP'}"
        )
        hb.set_title_widget(self.title_widget)
        tv.add_top_bar(hb)

        # Main layout
        main_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)

        # Left sidebar
        sb_scroller = Gtk.ScrolledWindow(vexpand=True)
        sb_scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        sb_scroller.set_size_request(185, -1)
        sb_scroller.add_css_class("bh-config-sidebar-scroll")

        self.nav_list = Gtk.ListBox(css_classes=["navigation-sidebar", "bh-config-sidebar"])
        self.nav_list.connect("row-selected", self._on_nav_selected)
        sb_scroller.set_child(self.nav_list)
        main_box.append(sb_scroller)

        main_box.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL))

        # Right content stack
        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE, hexpand=True, vexpand=True)

        for key, label, icon in self.SECTIONS:
            row = Gtk.ListBoxRow()
            row.nav_key = key
            row_box = Gtk.Box(spacing=10, margin_top=8, margin_bottom=8, margin_start=12, margin_end=12)
            img = Gtk.Image.new_from_icon_name(icon)
            if key == "delete":
                row_box.add_css_class("destructive-action")
            row_box.append(img)
            row_box.append(Gtk.Label(label=label, xalign=0))
            row.set_child(row_box)
            self.nav_list.append(row)

        content_scroller = Gtk.ScrolledWindow(hexpand=True, vexpand=True)
        content_scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        content_scroller.set_child(self.stack)
        main_box.append(content_scroller)

        tv.set_content(main_box)

        # Select first row
        first_row = self.nav_list.get_row_at_index(0)
        if first_row:
            self.nav_list.select_row(first_row)

    def _get_site(self) -> dict:
        for item in self.win.last_data.get("sites", []):
            if item.get("name") == self.site_name:
                return item
        return self._initial_site

    def _on_nav_selected(self, _listbox, row) -> None:
        if not row:
            return
        key = getattr(row, "nav_key", None)
        if not key:
            return
        self._current_key = key
        self._update_header()
        self._show_panel(key)

    def _update_header(self) -> None:
        site = self._get_site()
        self.title_widget.set_title(f"Site modification [{site.get('domain', self.site_name)}]")
        self.title_widget.set_subtitle(f"{site.get('php', '')} · {site.get('server', 'nginx')} · {'HTTPS' if site.get('secure') else 'HTTP'}")

    def _show_panel(self, key: str) -> None:
        existing = self.stack.get_child_by_name(key)
        if existing:
            self.stack.remove(existing)
        panel = self._build_panel(key)
        self.stack.add_named(panel, key)
        self.stack.set_visible_child_name(key)

    def _build_panel(self, key: str) -> Gtk.Widget:
        if key == "domain":
            return self._build_domain_panel()
        elif key == "root":
            return self._build_root_panel()
        elif key == "config":
            return self._build_config_panel()
        elif key == "ssl":
            return self._build_ssl_panel()
        elif key == "php":
            return self._build_php_panel()
        elif key == "server":
            return self._build_server_panel()
        elif key == "share":
            return self._build_share_panel()
        elif key == "delete":
            return self._build_delete_panel()
        return Gtk.Box()

    def _build_domain_panel(self) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14, margin_top=18, margin_bottom=18, margin_start=18, margin_end=18)
        
        info_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, css_classes=["card", "bh-config-info-card"])
        info_card.append(Gtk.Label(label="A domain or subdomain per line. Default port is 80 (HTTP) / 443 (HTTPS).", xalign=0, css_classes=["dim-label"]))
        info_card.append(Gtk.Label(label="Format: enter subdomain label (e.g. 'api') or full alias (e.g. 'api.example.test').", xalign=0, css_classes=["dim-label", "caption"]))
        box.append(info_card)

        add_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        entry = Gtk.Entry(placeholder_text="Enter subdomain (e.g. api or blog.site.test)", hexpand=True)
        add_btn = Gtk.Button(label="Add", icon_name="list-add-symbolic", css_classes=["suggested-action"], valign=Gtk.Align.CENTER)
        add_box.append(entry)
        add_box.append(add_btn)
        box.append(add_box)

        list_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0, css_classes=["card"])
        box.append(list_container)

        def redraw_domains():
            while list_container.get_first_child():
                list_container.remove(list_container.get_first_child())
            
            site = self._get_site()
            scheme = "https" if site.get("secure") else "http"
            port = "443" if site.get("secure") else "80"

            # Table Header
            th = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8, margin_top=8, margin_bottom=8, margin_start=12, margin_end=12)
            th.append(Gtk.Label(label="Domain name", xalign=0, hexpand=True, css_classes=["dim-label", "caption"]))
            th.append(Gtk.Label(label="Port", width_chars=8, xalign=0.5, css_classes=["dim-label", "caption"]))
            th.append(Gtk.Label(label="Operate", width_chars=12, xalign=1, css_classes=["dim-label", "caption"]))
            list_container.append(th)
            list_container.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))

            # Primary domain row
            prow = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8, margin_top=6, margin_bottom=6, margin_start=12, margin_end=12)
            p_name_box = Gtk.Box(spacing=8, hexpand=True)
            p_name_btn = Gtk.Button(label=f"{scheme}://{site['domain']}", css_classes=["flat"], halign=Gtk.Align.START)
            p_name_btn.connect("clicked", lambda *_: _open(f"{scheme}://{site['domain']}"))
            p_name_box.append(p_name_btn)
            p_name_box.append(pill("Primary", "bh-pill-blue"))
            prow.append(p_name_box)
            prow.append(Gtk.Label(label=port, width_chars=8, xalign=0.5, css_classes=["dim-label"]))
            prow.append(Gtk.Label(label="Inoperable", width_chars=12, xalign=1, css_classes=["dim-label", "caption"]))
            list_container.append(prow)

            # Subdomain aliases
            aliases = site.get("aliases", [])
            for alias in aliases:
                list_container.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))
                arow = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8, margin_top=6, margin_bottom=6, margin_start=12, margin_end=12)
                a_btn = Gtk.Button(label=f"{scheme}://{alias}", css_classes=["flat"], hexpand=True, halign=Gtk.Align.START)
                a_btn.connect("clicked", lambda *_a, al=alias: _open(f"{scheme}://{al}"))
                arow.append(a_btn)
                arow.append(Gtk.Label(label=port, width_chars=8, xalign=0.5, css_classes=["dim-label"]))
                
                rm_btn = Gtk.Button(icon_name="user-trash-symbolic", tooltip_text="Remove subdomain", css_classes=["flat", "destructive-action"], halign=Gtk.Align.END)
                rm_btn.connect("clicked", lambda *_a, al=alias: on_remove_alias(al))
                arow.append(rm_btn)
                list_container.append(arow)

        def on_add_alias(*_):
            val = entry.get_text().strip()
            if val:
                entry.set_text("")
                site = self._get_site()
                self.win.run_verb(["site", "subdomain", "add", site["name"], val], "Adding subdomain…",
                                  force_root=_is_ols(site))
                GLib.timeout_add(1200, lambda: (self._update_header(), redraw_domains(), False)[2])

        def on_remove_alias(alias):
            site = self._get_site()
            self.win.run_verb(["site", "subdomain", "rm", site["name"], alias], f"Removing {alias}…",
                              force_root=_is_ols(site))
            GLib.timeout_add(1200, lambda: (self._update_header(), redraw_domains(), False)[2])

        add_btn.connect("clicked", on_add_alias)
        entry.connect("activate", on_add_alias)
        redraw_domains()
        return box

    def _build_root_panel(self) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14, margin_top=18, margin_bottom=18, margin_start=18, margin_end=18)
        
        box.append(Gtk.Label(label="Site Directory & Document Root", xalign=0, css_classes=["title-4"]))
        
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, css_classes=["card", "bh-config-card"])
        site = self._get_site()
        cur_root = site.get("root", "")

        card.append(Gtk.Label(label="Document Root Directory:", xalign=0, css_classes=["dim-label"]))
        
        path_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        entry = Gtk.Entry(text=cur_root, hexpand=True)
        browse_btn = Gtk.Button(label="Browse…", valign=Gtk.Align.CENTER)
        path_box.append(entry)
        path_box.append(browse_btn)
        card.append(path_box)

        def on_browse_clicked(*_):
            def on_pick(dialog, result):
                try:
                    f = dialog.select_folder_finish(result)
                    if f:
                        entry.set_text(f.get_path())
                except Exception:
                    pass
            dlg = Gtk.FileDialog()
            dlg.set_title(f"Select document root for {site['name']}")
            if entry.get_text() and os.path.isdir(entry.get_text()):
                dlg.set_initial_folder(Gio.File.new_for_path(entry.get_text()))
            dlg.select_folder(self, None, on_pick)

        browse_btn.connect("clicked", on_browse_clicked)

        apply_btn = Gtk.Button(label="Save Directory", css_classes=["suggested-action"], halign=Gtk.Align.START)
        def on_apply_root(*_):
            new_path = entry.get_text().strip()
            if new_path and new_path != cur_root:
                self.win.run_verb(["site", "root", site["name"], new_path], f"Changing root for {site['name']} → {new_path}…")
                GLib.timeout_add(1200, lambda: (self._show_panel("root"), False)[1])
        apply_btn.connect("clicked", on_apply_root)
        card.append(apply_btn)
        box.append(card)

        box.append(Gtk.Label(label="Quick Launch", xalign=0, css_classes=["title-4"]))
        actions_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, css_classes=["card", "bh-config-card"])
        actions_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        
        b_folder = Gtk.Button(label="Open Folder", icon_name="folder-symbolic")
        b_folder.connect("clicked", lambda *_: _open(entry.get_text() or site.get("root", "")))
        actions_row.append(b_folder)

        b_editor = Gtk.Button(label="Open in Editor", icon_name="text-editor-symbolic")
        b_editor.connect("clicked", lambda *_: _open_editor(entry.get_text() or site.get("root", "")))
        actions_row.append(b_editor)

        b_term = Gtk.Button(label="Open Terminal", icon_name="utilities-terminal-symbolic")
        b_term.connect("clicked", lambda *_: _open_terminal(entry.get_text() or site.get("root", "")))
        actions_row.append(b_term)

        actions_card.append(actions_row)
        box.append(actions_card)
        return box

    def _build_config_panel(self) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, margin_top=18, margin_bottom=18, margin_start=18, margin_end=18)
        
        site = self._get_site()
        srv = site.get("server", "nginx")
        srv = "ols" if srv in ("ols", "openlitespeed") else srv
        conf_path = f"{os.path.expanduser('~/.omniserv')}/{'apache' if srv == 'apache' else 'nginx'}/sites/{site['name']}.conf"
        
        top_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        lbl = Gtk.Label(label=f"Config: {conf_path}", xalign=0, hexpand=True, css_classes=["dim-label", "caption"], wrap=True)
        top_bar.append(lbl)
        
        reload_btn = Gtk.Button(icon_name="view-refresh-symbolic", tooltip_text="Reload file")
        top_bar.append(reload_btn)

        ext_btn = Gtk.Button(label="Open in Editor", icon_name="text-editor-symbolic")
        ext_btn.connect("clicked", lambda *_: _open_editor(conf_path))
        top_bar.append(ext_btn)
        
        box.append(top_bar)

        text_view = Gtk.TextView(editable=False, monospace=True, css_classes=["card", "bh-config-editor"])
        sc = Gtk.ScrolledWindow(vexpand=True, hexpand=True, min_content_height=280)
        sc.set_child(text_view)
        box.append(sc)

        def load_conf():
            if os.path.isfile(conf_path):
                try:
                    with open(conf_path, "r", errors="replace") as f:
                        text_view.get_buffer().set_text(f.read())
                except Exception as e:
                    text_view.get_buffer().set_text(f"# Error reading config: {e}")
            else:
                text_view.get_buffer().set_text(f"# Config file not found:\n# {conf_path}")

        reload_btn.connect("clicked", lambda *_: load_conf())
        load_conf()
        return box

    def _build_ssl_panel(self) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14, margin_top=18, margin_bottom=18, margin_start=18, margin_end=18)
        
        box.append(Gtk.Label(label="SSL / HTTPS Certificate", xalign=0, css_classes=["title-4"]))
        
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, css_classes=["card", "bh-config-card"])
        site = self._get_site()
        is_secure = bool(site.get("secure"))
        dom = site.get("domain", "")

        status_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        status_row.append(status_dot(is_secure))
        status_title = Gtk.Label(label="HTTPS (SSL) is Active" if is_secure else "HTTPS (SSL) is Disabled",
                                 xalign=0, css_classes=["bh-brand"])
        status_row.append(status_title)
        card.append(status_row)

        desc = Gtk.Label(
            label="This site has a trusted local SSL certificate generated via mkcert." if is_secure
            else "This site is currently accessible over HTTP only. Enable SSL to generate a trusted local mkcert HTTPS certificate.",
            xalign=0, wrap=True, css_classes=["dim-label"]
        )
        card.append(desc)

        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10, margin_top=6)
        if not is_secure:
            b_install = Gtk.Button(label="Install SSL (Enable HTTPS)", icon_name="security-high-symbolic", css_classes=["suggested-action"])
            def on_install_ssl(*_):
                self.win.run_verb(["secure", dom], f"Securing {dom}…")
                GLib.timeout_add(1500, lambda: (self._update_header(), self._show_panel("ssl"), False)[2])
            b_install.connect("clicked", on_install_ssl)
            btn_box.append(b_install)
        else:
            b_reinstall = Gtk.Button(label="Reinstall SSL (Fresh Cert)", icon_name="security-high-symbolic")
            def on_reinstall_ssl(*_):
                self.win.run_verb(["resecure", dom], f"Reinstalling SSL for {dom}…")
                GLib.timeout_add(1500, lambda: (self._update_header(), self._show_panel("ssl"), False)[2])
            b_reinstall.connect("clicked", on_reinstall_ssl)
            btn_box.append(b_reinstall)

            b_remove = Gtk.Button(label="Remove SSL", icon_name="security-low-symbolic", css_classes=["destructive-action"])
            def on_remove_ssl(*_):
                self.win.confirm(
                    f"Remove SSL from “{dom}”?", "The site keeps working over http://.",
                    lambda: (self.win.run_verb(["unsecure", dom], f"Removing SSL from {dom}…"),
                             GLib.timeout_add(1500, lambda: (self._update_header(), self._show_panel("ssl"), False)[2]))
                )
            b_remove.connect("clicked", on_remove_ssl)
            btn_box.append(b_remove)

        card.append(btn_box)
        box.append(card)
        return box

    def _build_php_panel(self) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14, margin_top=18, margin_bottom=18, margin_start=18, margin_end=18)
        
        box.append(Gtk.Label(label="PHP Version Management", xalign=0, css_classes=["title-4"]))
        
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, css_classes=["card", "bh-config-card"])
        site = self._get_site()
        cur_php = site.get("php", "").replace("php@", "")

        cur_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        cur_row.append(Gtk.Label(label="Current PHP Version:", xalign=0, css_classes=["dim-label"]))
        cur_row.append(Gtk.Label(label=f"PHP {cur_php}" if cur_php else "Default", xalign=0, css_classes=["bh-brand"]))
        card.append(cur_row)

        installed_php = [x["key"].replace("php@", "") for x in self.win.last_data.get("services", [])
                         if x["role"] == "php" and x["installed"]]
        php_choices = installed_php or [k.replace("php@", "") for k in PHP_KEYS]

        dd_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        dd_row.append(Gtk.Label(label="Select PHP Version:", xalign=0, width_chars=18))
        dd = Gtk.DropDown.new_from_strings(php_choices)
        if cur_php in php_choices:
            dd.set_selected(php_choices.index(cur_php))
        dd_row.append(dd)
        card.append(dd_row)

        info = Gtk.Label(label="Switching PHP version will update the FastCGI configuration in the virtual host and reload the web server.",
                         xalign=0, wrap=True, css_classes=["dim-label", "caption"])
        card.append(info)

        btn = Gtk.Button(label="Switch PHP Version", css_classes=["suggested-action"], halign=Gtk.Align.START)
        def on_switch_php(*_):
            v = php_choices[dd.get_selected()]
            self.win.run_verb(["site", "php", site["name"], v], f"Switching {site['name']} → PHP {v}…",
                              force_root=_is_ols(site))
            GLib.timeout_add(1500, lambda: (self._update_header(), self._show_panel("php"), False)[2])
        btn.connect("clicked", on_switch_php)
        card.append(btn)

        box.append(card)
        return box

    def _build_server_panel(self) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14, margin_top=18, margin_bottom=18, margin_start=18, margin_end=18)
        
        box.append(Gtk.Label(label="Web Server", xalign=0, css_classes=["title-4"]))
        
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, css_classes=["card", "bh-config-card"])
        site = self._get_site()
        cur_srv = site.get("server", "nginx")
        cur_srv = "ols" if cur_srv in ("ols", "openlitespeed") else cur_srv

        cur_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        cur_row.append(Gtk.Label(label="Current Web Server:", xalign=0, css_classes=["dim-label"]))
        cur_row.append(Gtk.Label(label={"nginx": "nginx (Direct PHP)", "apache": "Apache (Reverse Proxy)", "ols": "OpenLiteSpeed"}.get(cur_srv, cur_srv),
                                 xalign=0, css_classes=["bh-brand"]))
        card.append(cur_row)

        srv_choices = [
            ("nginx", "nginx", "Direct FastCGI handling, ultra-fast and lightweight (default)"),
            ("apache", "Apache", "Runs behind nginx reverse proxy; supports native .htaccess files"),
            ("ols", "OpenLiteSpeed", "Runs behind nginx; supports .htaccess and LiteSpeed Cache"),
        ]

        server_list_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        radio_group = None
        radios = {}

        for val, name, desc in srv_choices:
            r_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            check = Gtk.CheckButton(label=name)
            if radio_group is None:
                radio_group = check
            else:
                check.set_group(radio_group)
            if val == cur_srv:
                check.set_active(True)
            radios[val] = check
            
            sub = Gtk.Label(label=desc, xalign=0, css_classes=["dim-label", "caption"], margin_start=28)
            r_box.append(check)
            r_box.append(sub)
            server_list_box.append(r_box)

        card.append(server_list_box)

        btn = Gtk.Button(label="Switch Web Server", css_classes=["suggested-action"], halign=Gtk.Align.START)
        def on_switch_server(*_):
            chosen = next((val for val, check in radios.items() if check.get_active()), "nginx")
            if chosen != cur_srv:
                self.win.run_verb(["site", "server", site["name"], chosen], f"Switching {site['name']} → {chosen}…")
                GLib.timeout_add(1500, lambda: (self._update_header(), self._show_panel("server"), False)[2])
        btn.connect("clicked", on_switch_server)
        card.append(btn)

        box.append(card)
        return box

    def _build_share_panel(self) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14, margin_top=18, margin_bottom=18, margin_start=18, margin_end=18)
        
        box.append(Gtk.Label(label="Cloudflare Public Sharing", xalign=0, css_classes=["title-4"]))
        
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, css_classes=["card", "bh-config-card"])
        site = self._get_site()
        tunnel_url = site.get("tunnel", "")
        is_live = bool(tunnel_url)

        status_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        status_row.append(status_dot(is_live))
        status_row.append(Gtk.Label(label="Public Tunnel is Live" if is_live else "Public Sharing is Inactive",
                                    xalign=0, css_classes=["bh-brand"]))
        card.append(status_row)

        desc = Gtk.Label(
            label="Anyone with this public URL can securely reach your local site over the internet." if is_live
            else "Cloudflare Quick Tunnel gives this site a temporary public HTTPS address with no account or port-forwarding required.",
            xalign=0, wrap=True, css_classes=["dim-label"]
        )
        card.append(desc)

        if is_live:
            url_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            url_entry = Gtk.Entry(text=tunnel_url, editable=False, hexpand=True)
            cp_btn = Gtk.Button(icon_name="edit-copy-symbolic", tooltip_text="Copy link")
            cp_btn.connect("clicked", lambda *_: self.win._copy(tunnel_url))
            open_btn = Gtk.Button(icon_name="web-browser-symbolic", tooltip_text="Open in browser")
            open_btn.connect("clicked", lambda *_: _open(tunnel_url))
            url_row.append(url_entry)
            url_row.append(cp_btn)
            url_row.append(open_btn)
            card.append(url_row)

            stop_btn = Gtk.Button(label="Stop Sharing", css_classes=["destructive-action"], halign=Gtk.Align.START)
            def on_stop_share(*_):
                self.win.run_verb(["tunnel", "stop", site["name"]], f"Stopped sharing {site['name']}")
                GLib.timeout_add(1500, lambda: (self._update_header(), self._show_panel("share"), False)[2])
            stop_btn.connect("clicked", on_stop_share)
            card.append(stop_btn)
        else:
            start_btn = Gtk.Button(label="Start Sharing Publicly", icon_name="network-wireless-symbolic",
                                   css_classes=["suggested-action"], halign=Gtk.Align.START)
            def on_start_share(*_):
                self.win.site_share(site["name"])
                GLib.timeout_add(3000, lambda: (self._update_header(), self._show_panel("share"), False)[2])
            start_btn.connect("clicked", on_start_share)
            card.append(start_btn)

        box.append(card)
        return box

    def _build_delete_panel(self) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14, margin_top=18, margin_bottom=18, margin_start=18, margin_end=18)
        
        box.append(Gtk.Label(label="Danger Zone", xalign=0, css_classes=["title-4", "bh-step-err"]))
        
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, css_classes=["card", "bh-config-danger-card"])
        site = self._get_site()
        name = site["name"]

        warn_title = Gtk.Label(label=f"Delete “{name}”", xalign=0, css_classes=["title-4", "bh-step-err"])
        card.append(warn_title)

        warn_desc = Gtk.Label(
            label="Deleting this site will remove its virtual host configuration from the web server (Nginx/Apache). Your project files in the document root will not be deleted unless you choose to purge them.",
            xalign=0, wrap=True, css_classes=["dim-label"]
        )
        card.append(warn_desc)

        del_btn = Gtk.Button(label="Delete Site", icon_name="user-trash-symbolic",
                             css_classes=["destructive-action"], halign=Gtk.Align.START)
        def on_delete_clicked(*_):
            self.win.confirm(
                f"Delete site “{name}”?",
                "Removes the vhost. Tick purge in the next step to also drop files + DB.",
                lambda: (self.close(), self.win.run_verb(["site", "rm", name], f"Removing {name}…"))
            )
        del_btn.connect("clicked", on_delete_clicked)
        card.append(del_btn)

        box.append(card)
        return box


def build_site_row(win, s: dict) -> Adw.ActionRow:
    scheme = "https" if s.get("secure") else "http"
    root_path = s.get("root", "")
    server_type = s.get("server", "nginx")
    php_ver = s.get("php", "")

    subtitle_parts = [p for p in (php_ver, server_type, root_path) if p]
    subtitle = " · ".join(subtitle_parts) if subtitle_parts else f"{scheme}://"

    row = Adw.ActionRow(title=s.get("domain", s.get("name")), subtitle=subtitle)
    row.add_prefix(status_dot(s.get("enabled", True)))

    box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6, valign=Gtk.Align.CENTER)

    # Clean SSL & status badges
    if s.get("secure"):
        box.append(pill("🔒 SSL Active", "bh-pill-blue"))
    else:
        box.append(pill("HTTP", "bh-pill-off"))

    if s.get("tunnel"):
        shared = pill("🌐 Shared", "bh-pill-warn")
        shared.set_tooltip_text(f"Public URL: {s['tunnel']}")
        box.append(shared)

    aliases = s.get("aliases") or []
    if aliases:
        box.append(pill(f"{len(aliases)} aliases", "bh-pill-warn"))

    # Quick action button group
    actions_group = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2, margin_start=4)

    # 1. Open in Browser
    openb = Gtk.Button(icon_name="web-browser-symbolic", tooltip_text="Open in browser",
                       css_classes=["bh-quick-btn", "flat"])
    openb.connect("clicked", lambda *_: _open(f"{scheme}://{s['domain']}"))
    actions_group.append(openb)

    # 2. Open in Code Editor
    if root_path:
        ed_btn = Gtk.Button(icon_name="text-editor-symbolic", tooltip_text="Open in code editor",
                            css_classes=["bh-quick-btn", "flat"])
        ed_btn.connect("clicked", lambda *_: _open_editor(root_path))
        actions_group.append(ed_btn)

        # 3. Reveal in File Manager
        folder_btn = Gtk.Button(icon_name="folder-symbolic", tooltip_text="Reveal in file manager",
                                css_classes=["bh-quick-btn", "flat"])
        folder_btn.connect("clicked", lambda *_: _open(root_path))
        actions_group.append(folder_btn)

        # 4. Open Terminal
        term_btn = Gtk.Button(icon_name="utilities-terminal-symbolic", tooltip_text="Open terminal in root",
                              css_classes=["bh-quick-btn", "flat"])
        term_btn.connect("clicked", lambda *_: _open_terminal(root_path))
        actions_group.append(term_btn)

    # 5. Site Settings / Config dialog
    cfg_btn = Gtk.Button(icon_name="view-more-symbolic", tooltip_text="Site settings",
                         css_classes=["bh-quick-btn", "flat"])
    cfg_btn.connect("clicked", lambda *_: SiteConfigDialog(win, s).present())
    actions_group.append(cfg_btn)

    box.append(actions_group)
    row.add_suffix(box)
    return row


def _set_badge(badge: Gtk.Label, text: str, css: str) -> None:
    for c in ("bh-pill-on", "bh-pill-off", "bh-pill-warn", "bh-pill-blue"):
        badge.remove_css_class(c)
    badge.add_css_class(css)
    badge.set_label(text)


def _set_dot(img: Gtk.Image, on: bool) -> None:
    img.remove_css_class("dot-on")
    img.remove_css_class("dot-off")
    img.add_css_class("dot-on" if on else "dot-off")


class CardGrid(Gtk.Grid):
    """Responsive grid of equal-width cards — the GTK equivalent of the Windows dashboard's
    4×`*`-column Grid: every card is STRETCHED to an equal share of the width (so 4 always
    fill a row, never 3+1), and the column count reflows 4 → 2 → 1 as the window narrows.
    A FlowBox can't do this (it sizes to the widest card's natural width, not a forced N)."""
    __gtype_name__ = "BHCardGrid"

    def __init__(self) -> None:
        super().__init__(column_spacing=12, row_spacing=12, column_homogeneous=True, hexpand=True)
        self._cards: list[Gtk.Widget] = []
        self._cols = 0

    def add_card(self, w: Gtk.Widget) -> None:
        w.set_hexpand(True)
        w.set_halign(Gtk.Align.FILL)
        i = len(self._cards)
        self._cards.append(w)
        self.attach(w, i % 4, i // 4, 1, 1)   # provisional 4-col (a sane default); do_size_allocate refines

    def do_measure(self, orientation, for_size):
        minimum, natural, min_b, nat_b = Gtk.Grid.do_measure(self, orientation, for_size)
        if orientation == Gtk.Orientation.HORIZONTAL and self._cards:
            # A homogeneous N-col Grid reports its FULL N-column min width as its minimum. That pins
            # the whole window wide and PREVENTS the narrowing that would trigger the 4→2→1 reflow
            # (chicken-and-egg: can't shrink to reflow because the un-reflowed min blocks shrinking).
            # Report a SINGLE card's min instead — the window can then narrow, do_size_allocate fires
            # with the smaller width, and we reflow to fit. Cards wrap/ellipsize so they never clip.
            one = 0
            for c in self._cards:
                cm = c.measure(Gtk.Orientation.HORIZONTAL, -1)[0]
                if cm > one:
                    one = cm
            return (one, natural, min_b, nat_b)
        return (minimum, natural, min_b, nat_b)

    def do_size_allocate(self, width: int, height: int, baseline: int) -> None:
        cols = 4 if width >= 700 else 2 if width >= 360 else 1
        if cols != self._cols:
            self._cols = cols
            GLib.idle_add(self._relayout, cols)          # defer: never mutate layout inside allocate
        Gtk.Grid.do_size_allocate(self, width, height, baseline)

    def _relayout(self, cols: int) -> bool:
        for c in list(self._cards):
            if c.get_parent() is self:
                self.remove(c)
        for i, c in enumerate(self._cards):
            self.attach(c, i % cols, i // cols, 1, 1)
        return False
