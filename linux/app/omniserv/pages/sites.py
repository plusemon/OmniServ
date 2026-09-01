"""Sites pane: professional flat dashboard-style website management with overview cards,
inline category filters, and clean categorized virtual host rows.
"""
from __future__ import annotations

import os
import shutil
import subprocess

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk, Pango  # noqa: E402

from ..widgets import pill, status_dot, status_pill
from ._shared import (
    CardGrid,
    SiteConfigDialog,
    _open,
    _open_text_editor,
    _open_terminal,
    clean_version,
    is_tool,
)

SITE_GROUPS_DEF = [
    ("Nginx Websites", "nginx"),
    ("Apache Websites", "apache"),
    ("OpenLiteSpeed Websites", "ols openlitespeed"),
    ("Other Websites", "other"),
]

FILTER_CHIPS = [
    ("all", "All"),
    ("ssl", "HTTPS / SSL"),
    ("http", "HTTP Only"),
    ("shared", "Shared"),
    ("nginx", "Nginx"),
    ("apache", "Apache"),
    ("ols", "OpenLiteSpeed"),
]


class SitesPage(Gtk.Box):
    def __init__(self, win) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.win = win
        self._current_filter = "all"
        self._search_query = ""
        self._last_sites: list[dict] = []
        self._last_services: list[dict] = []
        self._last_config: dict = {}
        self._sig = None

        self.scroller = Gtk.ScrolledWindow(vexpand=True, hexpand=True)
        self.scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.body = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=18,
            margin_top=18,
            margin_bottom=18,
            margin_start=18,
            margin_end=18,
        )
        self.scroller.set_child(self.body)
        self.append(self.scroller)

        # ── 1. Header: title + subtitle + master action buttons ──
        head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        tb = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
        tb.append(Gtk.Label(label="Websites", xalign=0, css_classes=["title-1"]))
        self.subtitle = Gtk.Label(
            label="Manage local virtual hosts, SSL certificates, PHP versions, and public tunnels",
            xalign=0,
            css_classes=["dim-label"],
        )
        tb.append(self.subtitle)
        head.append(tb)

        btn_group = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=8,
            valign=Gtk.Align.CENTER,
        )

        actions_linked = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            css_classes=["bh-button-group", "linked"],
        )
        self.reload_btn = Gtk.Button(
            label="Reload web", icon_name="view-refresh-symbolic", tooltip_text="Reload web server virtual hosts"
        )
        self.reload_btn.connect(
            "clicked",
            lambda *_: self.win.run_verb(["reload"], "Reloading web server…"),
        )
        self.folder_btn = Gtk.Button(
            icon_name="folder-symbolic", tooltip_text="Open websites folder"
        )
        self.folder_btn.connect("clicked", lambda *_: self._open_sites_folder())
        actions_linked.append(self.reload_btn)
        actions_linked.append(self.folder_btn)
        btn_group.append(actions_linked)

        self.add_site_btn = Gtk.Button(
            label="Add site",
            icon_name="list-add-symbolic",
            css_classes=["suggested-action"],
        )
        self.add_site_btn.connect("clicked", lambda *_: self.win.add_site_dialog())
        btn_group.append(self.add_site_btn)

        head.append(btn_group)
        self.body.append(head)

        # ── 2. Top Summary Metric Cards (CardGrid matching Services / Dashboard) ──
        cards = CardGrid()
        self.c_sites = self._metric_card("Websites")
        self.c_ssl = self._metric_card("SSL / Security")
        self.c_web = self._metric_card("Web Server")
        self.c_php = self._metric_card("Default PHP")
        for c in (
            self.c_sites["card"],
            self.c_ssl["card"],
            self.c_web["card"],
            self.c_php["card"],
        ):
            cards.add_card(c)
        self.body.append(cards)

        # ── 3. Clean Inline Search & Category Filter Toolbar ──
        filter_bar = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=10,
            valign=Gtk.Align.CENTER,
        )

        self.search_entry = Gtk.SearchEntry(
            placeholder_text="Search websites (e.g. domain, php, server, path)…",
        )
        self.search_entry.set_size_request(280, -1)
        self.search_entry.connect("search-changed", self._on_search_changed)
        filter_bar.append(self.search_entry)

        # Filter Chips
        self.chips_row = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL, spacing=6
        )
        self._chip_buttons: dict[str, Gtk.ToggleButton] = {}
        for f_key, f_label in FILTER_CHIPS:
            btn = Gtk.ToggleButton(
                label=f_label,
                active=(f_key == "all"),
                css_classes=["bh-filter-chip"],
            )
            btn.connect("toggled", lambda b, k=f_key: self._on_chip_toggled(k, b))
            self._chip_buttons[f_key] = btn
            self.chips_row.append(btn)
        filter_bar.append(self.chips_row)

        self.body.append(filter_bar)

        # ── 4. Categorized Virtual Hosts Section Container ──
        self.list_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        self.body.append(self.list_container)

        # Empty status page
        self.empty_page = Adw.StatusPage(
            icon_name="system-search-symbolic",
            title="No matching websites",
            description="Try clearing your search query or clicking “Add site” to create a new website.",
        )
        self.empty_page.set_visible(False)
        self.body.append(self.empty_page)

    # ── Metric Card Builder (Matching Services / Dashboard status cards) ──
    def _metric_card(self, title: str) -> dict:
        card = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=4,
            css_classes=["card", "bh-metric"],
        )
        top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        top.append(
            Gtk.Label(
                label=title,
                xalign=0,
                hexpand=True,
                css_classes=["bh-metric-cap", "dim-label"],
            )
        )
        badge = pill("● Inactive", "bh-pill-off")
        top.append(badge)
        card.append(top)

        val = Gtk.Label(
            label="—",
            xalign=0,
            css_classes=["bh-metric-val"],
            wrap=True,
            wrap_mode=Pango.WrapMode.WORD_CHAR,
            max_width_chars=18,
        )
        sub = Gtk.Label(label="", xalign=0, css_classes=["dim-label", "caption"])
        card.append(val)
        card.append(sub)
        return {"card": card, "val": val, "sub": sub, "badge": badge}

    def _set_card_badge(self, badge: Gtk.Label, text: str, css: str) -> None:
        for c in ("bh-pill-on", "bh-pill-off", "bh-pill-warn", "bh-pill-blue"):
            badge.remove_css_class(c)
        badge.add_css_class(css)
        badge.set_label(text)

    # ── Folder Opener Helper ──
    def _open_sites_folder(self) -> None:
        for candidate in (
            os.path.expanduser("~/Sites"),
            os.path.expanduser("~/OmniServ/www"),
            os.path.expanduser("~/.omniserv"),
        ):
            if os.path.isdir(candidate):
                _open(candidate)
                return
        _open(os.path.expanduser("~"))

    # ── Filters & Search Handlers ──
    def _on_search_changed(self, entry: Gtk.SearchEntry) -> None:
        self._search_query = entry.get_text().strip().lower()
        self._render_sites()

    def _on_chip_toggled(self, key: str, button: Gtk.ToggleButton) -> None:
        if not button.get_active():
            if self._current_filter == key:
                button.set_active(True)
            return

        self._current_filter = key
        for k, b in self._chip_buttons.items():
            if k != key and b.get_active():
                b.set_active(False)
        self._render_sites()

    def _matches_filter(self, s: dict) -> bool:
        if self._search_query:
            q = self._search_query
            name = s.get("name", "").lower()
            dom = s.get("domain", "").lower()
            php = s.get("php", "").lower()
            srv = s.get("server", "").lower()
            root = s.get("root", "").lower()
            aliases = " ".join(s.get("aliases", [])).lower()
            if not (q in name or q in dom or q in php or q in srv or q in root or q in aliases):
                return False

        f = self._current_filter
        if f == "all":
            return True
        elif f == "ssl":
            return bool(s.get("secure"))
        elif f == "http":
            return not bool(s.get("secure"))
        elif f == "shared":
            return bool(s.get("tunnel"))
        elif f == "nginx":
            return s.get("server", "nginx") in ("nginx", "")
        elif f == "apache":
            return s.get("server") == "apache"
        elif f == "ols":
            return s.get("server") in ("ols", "openlitespeed")
        return True

    def _site_in_group(self, s: dict, roles: str) -> bool:
        srv = s.get("server", "nginx").lower()
        if not srv:
            srv = "nginx"
        if roles == "other":
            return srv not in ("nginx", "apache", "ols", "openlitespeed")
        return srv in roles.split()

    # ── Refresh & Metrics Calculation ──
    def refresh(self, data: dict) -> None:
        all_sites = data.get("sites", [])
        services = data.get("services", [])
        cfg = data.get("config", {})

        # Exclude built-in tools (phpMyAdmin / Adminer / Mailpit)
        sites = [s for s in all_sites if not is_tool(s.get("name", ""))]
        self._last_sites = sites
        self._last_services = services
        self._last_config = cfg

        sig = (
            tuple(
                (
                    s.get("name"),
                    s.get("domain"),
                    s.get("secure"),
                    s.get("enabled"),
                    s.get("server"),
                    s.get("php"),
                    s.get("root"),
                    s.get("tunnel"),
                    tuple(s.get("aliases") or []),
                )
                for s in sites
            ),
            cfg.get("default_php"),
            cfg.get("default_web"),
        )

        self._update_metrics(sites, cfg, services)
        self._update_chip_labels(sites)

        if sig == self._sig:
            return
        self._sig = sig
        self._render_sites()

    def _update_metrics(self, sites: list[dict], cfg: dict, services: list[dict]) -> None:
        total_sites = len(sites)
        ssl_count = sum(1 for s in sites if s.get("secure"))
        tunnel_count = sum(1 for s in sites if s.get("tunnel"))

        def_php = cfg.get("default_php", "php@8.5")
        def_web = cfg.get("default_web", "nginx")

        nginx_count = sum(1 for s in sites if s.get("server", "nginx") in ("nginx", ""))
        apache_count = sum(1 for s in sites if s.get("server") == "apache")
        ols_count = sum(1 for s in sites if s.get("server") in ("ols", "openlitespeed"))
        custom_php_count = sum(1 for s in sites if s.get("php") and s.get("php") != def_php)

        self.subtitle.set_label(
            f"{total_sites} websites configured · {ssl_count} HTTPS secure · Defaults: {def_php}, {def_web}"
        )

        # 1. Total Websites Card
        self.c_sites["val"].set_label(f"{total_sites} Sites" if total_sites != 1 else "1 Site")
        self.c_sites["sub"].set_label(f"{total_sites} active vhosts · {tunnel_count} public")
        self._set_card_badge(
            self.c_sites["badge"],
            "● Active" if total_sites > 0 else "● Empty",
            "bh-pill-on" if total_sites > 0 else "bh-pill-off",
        )

        # 2. SSL / Security Card
        self.c_ssl["val"].set_label(f"{ssl_count} Secured")
        if total_sites > 0 and ssl_count == total_sites:
            self.c_ssl["sub"].set_label("All virtual hosts encrypted")
        else:
            self.c_ssl["sub"].set_label(f"{total_sites - ssl_count} unencrypted HTTP")
        self._set_card_badge(
            self.c_ssl["badge"],
            "● mkcert TLS" if ssl_count > 0 else "● Insecure",
            "bh-pill-blue" if ssl_count > 0 else "bh-pill-off",
        )

        # 3. Web Server Card
        web_running = any(s.get("role") == "web" and s.get("running") for s in services)
        self.c_web["val"].set_label(def_web.title())
        self.c_web["sub"].set_label(f"{nginx_count} nginx · {apache_count} apache · {ols_count} ols")
        self._set_card_badge(
            self.c_web["badge"],
            "● Live" if web_running else "● Default",
            "bh-pill-on" if web_running else "bh-pill-blue",
        )

        # 4. Default PHP Card
        php_running = any(s.get("role") == "php" and s.get("running") for s in services)
        self.c_php["val"].set_label(def_php)
        if custom_php_count > 0:
            self.c_php["sub"].set_label(f"{custom_php_count} custom PHP overrides")
        else:
            self.c_php["sub"].set_label("Default CLI & FastCGI")
        self._set_card_badge(
            self.c_php["badge"],
            "● Active" if php_running else "● Default",
            "bh-pill-on" if php_running else "bh-pill-blue",
        )

    def _update_chip_labels(self, sites: list[dict]) -> None:
        counts = {
            "all": len(sites),
            "ssl": sum(1 for s in sites if s.get("secure")),
            "http": sum(1 for s in sites if not s.get("secure")),
            "shared": sum(1 for s in sites if s.get("tunnel")),
            "nginx": sum(1 for s in sites if s.get("server", "nginx") in ("nginx", "")),
            "apache": sum(1 for s in sites if s.get("server") == "apache"),
            "ols": sum(1 for s in sites if s.get("server") in ("ols", "openlitespeed")),
        }
        for k, btn in self._chip_buttons.items():
            base_label = next(lbl for key, lbl in FILTER_CHIPS if key == k)
            count = counts.get(k, 0)
            btn.set_label(f"{base_label} ({count})")

    # ── Section & Rows Rendering ──
    def _render_sites(self) -> None:
        adj = self.scroller.get_vadjustment()
        pos = adj.get_value() if adj else 0.0

        child = self.list_container.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self.list_container.remove(child)
            child = nxt

        total_visible_rows = 0

        for title, roles in SITE_GROUPS_DEF:
            group_sites = [
                s
                for s in self._last_sites
                if self._site_in_group(s, roles) and self._matches_filter(s)
            ]
            if not group_sites:
                continue

            total_visible_rows += len(group_sites)

            # Section Header (Services page pattern)
            grp_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            hdr_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)

            lbl = Gtk.Label(label=title, xalign=0, css_classes=["title-4"])
            hdr_box.append(lbl)

            sec_in_grp = sum(1 for s in group_sites if s.get("secure"))
            if sec_in_grp > 0:
                hdr_box.append(pill(f"{sec_in_grp} secure", "bh-pill-blue"))

            hdr_box.append(Gtk.Box(hexpand=True))
            hdr_box.append(
                Gtk.Label(
                    label=f"{len(group_sites)} site{'s' if len(group_sites) != 1 else ''}",
                    css_classes=["dim-label", "caption"],
                )
            )
            grp_box.append(hdr_box)

            # Boxed List (Matching Dashboard Websites & Services pattern)
            listbox = Gtk.ListBox(
                selection_mode=Gtk.SelectionMode.NONE,
                css_classes=["boxed-list"],
            )
            for s in group_sites:
                listbox.append(self._build_site_row(s))
            grp_box.append(listbox)

            self.list_container.append(grp_box)

        has_visible = total_visible_rows > 0
        self.list_container.set_visible(has_visible)
        self.empty_page.set_visible(not has_visible)

        if adj and pos:
            GLib.idle_add(lambda a=adj, p=pos: (a.set_value(p), False)[1])

    # ── Flat, Clean Site Row (Matching Services & Dashboard pattern) ──
    def _build_site_row(self, s: dict) -> Adw.ActionRow:
        scheme = "https" if s.get("secure") else "http"
        domain = s.get("domain", s.get("name", ""))
        name = s.get("name", "")
        root_path = s.get("root", "")
        server_type = s.get("server", "nginx")
        php_ver = s.get("php", "")
        clean_php = clean_version(php_ver) if php_ver else ""

        subtitle_parts = []
        if clean_php:
            subtitle_parts.append(f"PHP {clean_php}")
        elif php_ver:
            subtitle_parts.append(php_ver)
        if server_type:
            subtitle_parts.append(server_type)
        if root_path:
            subtitle_parts.append(root_path)

        subtitle = " · ".join(subtitle_parts) if subtitle_parts else f"{scheme}://{domain}"

        # Row Title & Subtitle
        row = Adw.ActionRow(title=domain, subtitle=subtitle)
        row.set_activatable(True)
        row.connect("activated", lambda *_: SiteConfigDialog(self.win, s).present())

        # Status Dot (Clean 14px dot on the left)
        row.add_prefix(status_dot(s.get("enabled", True)))

        # Suffix: Badges + Action Buttons
        suffix = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6, valign=Gtk.Align.CENTER)

        # 1. SSL Badge
        if s.get("secure"):
            suffix.append(pill("🔒 SSL Active", "bh-pill-blue"))
        else:
            suffix.append(pill("HTTP", "bh-pill-off"))

        # 2. Cloudflare Shared Tunnel Badge
        if s.get("tunnel"):
            shared = pill("🌐 Shared", "bh-pill-warn")
            shared.set_tooltip_text(f"Public URL: {s['tunnel']}")
            suffix.append(shared)

        # 3. Subdomain Aliases Badge
        aliases = s.get("aliases") or []
        if aliases:
            suffix.append(pill(f"{len(aliases)} aliases", "bh-pill-warn"))

        # 4. Quick Action Button Group (Flat icon buttons)
        actions_group = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL, spacing=2, margin_start=4
        )

        # Open in Browser
        openb = Gtk.Button(
            icon_name="web-browser-symbolic",
            tooltip_text=f"Open {scheme}://{domain}",
            css_classes=["bh-quick-btn", "flat"],
        )
        openb.connect("clicked", lambda *_: _open(f"{scheme}://{domain}"))
        actions_group.append(openb)

        # File & Directory Shortcuts
        if root_path:
            ed_btn = Gtk.Button(
                icon_name="text-editor-symbolic",
                tooltip_text="Open project in text editor",
                css_classes=["bh-quick-btn", "flat"],
            )
            ed_btn.connect("clicked", lambda *_: _open_text_editor(root_path))
            actions_group.append(ed_btn)

            folder_btn = Gtk.Button(
                icon_name="folder-symbolic",
                tooltip_text="Reveal in file manager",
                css_classes=["bh-quick-btn", "flat"],
            )
            folder_btn.connect("clicked", lambda *_: _open(root_path))
            actions_group.append(folder_btn)

            term_btn = Gtk.Button(
                icon_name="utilities-terminal-symbolic",
                tooltip_text="Open terminal in document root",
                css_classes=["bh-quick-btn", "flat"],
            )
            term_btn.connect("clicked", lambda *_: _open_terminal(root_path))
            actions_group.append(term_btn)

        # Site Configuration Dialog
        cfg_btn = Gtk.Button(
            icon_name="preferences-system-symbolic",
            tooltip_text="Site settings & virtual host config",
            css_classes=["bh-quick-btn", "flat"],
        )
        cfg_btn.connect("clicked", lambda *_: SiteConfigDialog(self.win, s).present())
        actions_group.append(cfg_btn)

        # Delete Site Action
        del_btn = Gtk.Button(
            icon_name="user-trash-symbolic",
            tooltip_text=f"Delete {name}",
            css_classes=["bh-quick-btn", "flat", "destructive-action"],
        )
        del_btn.connect(
            "clicked",
            lambda *_: self.win.confirm(
                f"Delete site “{name}”?",
                "Removes the virtual host. Tick purge in the next step to also drop files + DB.",
                lambda: self.win.run_verb(["site", "rm", name], f"Removing {name}…"),
            ),
        )
        actions_group.append(del_btn)

        suffix.append(actions_group)
        row.add_suffix(suffix)
        return row
