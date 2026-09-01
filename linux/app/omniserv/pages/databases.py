"""Databases pane: professional flat dashboard-style database management with overview cards,
database server controls, inline filters, and clean managed database rows.
"""
from __future__ import annotations

import json

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk, Pango  # noqa: E402

from ..widgets import pill, status_dot, status_pill
from ._shared import CardGrid, _open, clean_version

DB_FILTER_CHIPS = [
    ("all", "All"),
    ("mysql", "MariaDB / MySQL"),
    ("pg", "PostgreSQL"),
]


class DatabasesPage(Gtk.Box):
    def __init__(self, win) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.win = win
        self._current_filter = "all"
        self._search_query = ""
        self._last_services: list[dict] = []
        self._last_dbs: list[dict] = []
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

        # ── 1. Header: title + subtitle + action buttons ──
        head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        tb = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
        tb.append(Gtk.Label(label="Databases", xalign=0, css_classes=["title-1"]))
        self.subtitle = Gtk.Label(
            label="Manage MariaDB, MySQL, and PostgreSQL database servers and user databases",
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
        self.root_pwd_btn = Gtk.Button(
            label="Root password",
            icon_name="dialog-password-symbolic",
            tooltip_text="Configure MySQL / MariaDB root password",
        )
        self.root_pwd_btn.connect("clicked", lambda *_: self.win.db_root_dialog())
        actions_linked.append(self.root_pwd_btn)
        btn_group.append(actions_linked)

        self.create_db_btn = Gtk.Button(
            label="Create database",
            icon_name="list-add-symbolic",
            css_classes=["suggested-action"],
        )
        self.create_db_btn.connect("clicked", lambda *_: self.win.create_db_dialog())
        btn_group.append(self.create_db_btn)

        head.append(btn_group)
        self.body.append(head)

        # ── 2. Top Summary Metric Cards (CardGrid matching Services / Sites) ──
        cards = CardGrid()
        self.c_my = self._metric_card("MySQL / MariaDB")
        self.c_pg = self._metric_card("PostgreSQL")
        self.c_dbs = self._metric_card("Total Databases")
        self.c_tools = self._metric_card("Web Management")
        for c in (
            self.c_my["card"],
            self.c_pg["card"],
            self.c_dbs["card"],
            self.c_tools["card"],
        ):
            cards.add_card(c)
        self.body.append(cards)

        # ── 3. Database Servers & Engines Section ──
        self.servers_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.body.append(self.servers_container)

        # ── 4. Clean Inline Search & Category Filter Toolbar for Databases ──
        filter_bar = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=10,
            valign=Gtk.Align.CENTER,
        )

        self.search_entry = Gtk.SearchEntry(
            placeholder_text="Search databases (e.g. name, engine)…",
        )
        self.search_entry.set_size_request(280, -1)
        self.search_entry.connect("search-changed", self._on_search_changed)
        filter_bar.append(self.search_entry)

        # Filter Chips
        self.chips_row = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL, spacing=6
        )
        self._chip_buttons: dict[str, Gtk.ToggleButton] = {}
        for f_key, f_label in DB_FILTER_CHIPS:
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

        # ── 5. Managed Databases Section ──
        self.dbs_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.body.append(self.dbs_container)

        # Empty status page
        self.empty_page = Adw.StatusPage(
            icon_name="system-search-symbolic",
            title="No matching databases",
            description="Try clearing your search query or clicking “Create database” to add one.",
        )
        self.empty_page.set_visible(False)
        self.body.append(self.empty_page)

    # ── Metric Card Builder ──
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

    # ── Filters & Search Handlers ──
    def _on_search_changed(self, entry: Gtk.SearchEntry) -> None:
        self._search_query = entry.get_text().strip().lower()
        self._render_dbs_section()

    def _on_chip_toggled(self, key: str, button: Gtk.ToggleButton) -> None:
        if not button.get_active():
            if self._current_filter == key:
                button.set_active(True)
            return

        self._current_filter = key
        for k, b in self._chip_buttons.items():
            if k != key and b.get_active():
                b.set_active(False)
        self._render_dbs_section()

    def _matches_filter(self, d: dict) -> bool:
        if self._search_query:
            q = self._search_query
            name = d.get("name", "").lower()
            engine = d.get("engine", "mysql").lower()
            if not (q in name or q in engine):
                return False

        f = self._current_filter
        engine = d.get("engine", "mysql").lower()
        if f == "all":
            return True
        elif f == "mysql":
            return engine in ("mysql", "mariadb")
        elif f == "pg":
            return engine in ("pg", "postgresql")
        return True

    # ── Refresh & Rendering ──
    def refresh(self, data: dict) -> None:
        services = data.get("services", [])
        self._last_services = services

        # Load databases list via engine
        _rc, out = self.win.engine.run("db", "list", "--json")
        items = []
        if "[" in out:
            try:
                items = json.loads(out[out.find("[") : out.rfind("]") + 1])
            except Exception:
                items = []
        self._last_dbs = items

        db_svcs = [x for x in services if x.get("role") == "db"]
        sig = (
            tuple(
                (
                    s["key"],
                    s.get("installed"),
                    s.get("running"),
                    s.get("version", ""),
                )
                for s in db_svcs
            ),
            tuple((d.get("name"), d.get("engine")) for d in items),
        )

        self._update_metrics(db_svcs, items)
        self._update_chip_labels(items)

        if sig == self._sig:
            return
        self._sig = sig

        self._render_servers_section(db_svcs)
        self._render_dbs_section()

    def _update_metrics(self, db_svcs: list[dict], dbs: list[dict]) -> None:
        total_dbs = len(dbs)
        my_dbs = sum(1 for d in dbs if d.get("engine", "mysql") in ("mysql", "mariadb"))
        pg_dbs = sum(1 for d in dbs if d.get("engine", "mysql") in ("pg", "postgresql"))

        # 1. MariaDB / MySQL status
        my_running_svcs = [s for s in db_svcs if s["key"] in ("mariadb", "mysql") and s.get("running")]
        my_installed_svcs = [s for s in db_svcs if s["key"] in ("mariadb", "mysql") and s.get("installed")]
        if my_running_svcs:
            svc = my_running_svcs[0]
            v = clean_version(svc.get("version", ""))
            self.c_my["val"].set_label(svc["key"].title() + (f" {v}" if v else ""))
            self.c_my["sub"].set_label("Port 3306 · Active MySQL service")
            self._set_card_badge(self.c_my["badge"], "● Running", "bh-pill-on")
        elif my_installed_svcs:
            svc = my_installed_svcs[0]
            self.c_my["val"].set_label(svc["key"].title())
            self.c_my["sub"].set_label("Service stopped · Port 3306")
            self._set_card_badge(self.c_my["badge"], "● Stopped", "bh-pill-off")
        else:
            self.c_my["val"].set_label("Not installed")
            self.c_my["sub"].set_label("MariaDB / MySQL engine")
            self._set_card_badge(self.c_my["badge"], "● Inactive", "bh-pill-off")

        # 2. PostgreSQL status
        pg_running_svcs = [s for s in db_svcs if s["key"].startswith("postgresql") and s.get("running")]
        pg_installed_svcs = [s for s in db_svcs if s["key"].startswith("postgresql") and s.get("installed")]
        if pg_running_svcs:
            svc = pg_running_svcs[0]
            v = clean_version(svc.get("version", ""))
            self.c_pg["val"].set_label(svc["key"].replace("postgresql", "PostgreSQL ") + (f" {v}" if v else ""))
            self.c_pg["sub"].set_label("Port 5432 · Active PG engine")
            self._set_card_badge(self.c_pg["badge"], "● Running", "bh-pill-on")
        elif pg_installed_svcs:
            svc = pg_installed_svcs[0]
            self.c_pg["val"].set_label(svc["key"].replace("postgresql", "PostgreSQL "))
            self.c_pg["sub"].set_label("Service stopped · Port 5432")
            self._set_card_badge(self.c_pg["badge"], "● Stopped", "bh-pill-off")
        else:
            self.c_pg["val"].set_label("Not installed")
            self.c_pg["sub"].set_label("PostgreSQL engine")
            self._set_card_badge(self.c_pg["badge"], "● Inactive", "bh-pill-off")

        # 3. Total databases
        self.c_dbs["val"].set_label(f"{total_dbs} Databases" if total_dbs != 1 else "1 Database")
        self.c_dbs["sub"].set_label(f"{my_dbs} MariaDB/MySQL · {pg_dbs} PostgreSQL")
        self._set_card_badge(
            self.c_dbs["badge"],
            "● Active" if total_dbs > 0 else "● Empty",
            "bh-pill-on" if total_dbs > 0 else "bh-pill-off",
        )

        # 4. Web tools
        all_running = len(my_running_svcs) + len(pg_running_svcs)
        self.c_tools["val"].set_label("phpMyAdmin / Adminer")
        self.c_tools["sub"].set_label("Web-based database manager")
        self._set_card_badge(
            self.c_tools["badge"],
            "● Ready" if all_running > 0 else "● Offline",
            "bh-pill-blue" if all_running > 0 else "bh-pill-off",
        )

        self.subtitle.set_label(
            f"{total_dbs} databases managed · {all_running} active database servers · Default ports 3306, 5432"
        )

    def _update_chip_labels(self, dbs: list[dict]) -> None:
        counts = {
            "all": len(dbs),
            "mysql": sum(1 for d in dbs if d.get("engine", "mysql") in ("mysql", "mariadb")),
            "pg": sum(1 for d in dbs if d.get("engine", "mysql") in ("pg", "postgresql")),
        }
        for k, btn in self._chip_buttons.items():
            base_label = next(lbl for key, lbl in DB_FILTER_CHIPS if key == k)
            count = counts.get(k, 0)
            btn.set_label(f"{base_label} ({count})")

    # ── Servers Section ──
    def _render_servers_section(self, db_svcs: list[dict]) -> None:
        child = self.servers_container.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self.servers_container.remove(child)
            child = nxt

        hdr_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        hdr_box.append(Gtk.Label(label="Database Engines & Servers", xalign=0, css_classes=["title-4"]))
        running_cnt = sum(1 for s in db_svcs if s.get("running"))
        if running_cnt > 0:
            hdr_box.append(pill(f"{running_cnt} active", "bh-pill-on"))
        hdr_box.append(Gtk.Box(hexpand=True))
        hdr_box.append(Gtk.Label(label=f"{len(db_svcs)} engines", css_classes=["dim-label", "caption"]))
        self.servers_container.append(hdr_box)

        # root-password check
        my_running = any(s["key"] in ("mariadb", "mysql") and s.get("running") for s in db_svcs)
        root_status = ""
        if my_running:
            _rc, out = self.win.engine.run("db", "root-status")
            root_status = out.strip().splitlines()[-1].strip() if out.strip() else ""

        listbox = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE, css_classes=["boxed-list"])

        for s in db_svcs:
            key = s["key"]
            is_my = key in ("mariadb", "mysql")
            installed = s.get("installed", False)
            running = s.get("running", False)
            v = clean_version(s.get("version", "")) or s.get("formula", "")

            sub_parts = []
            if v:
                sub_parts.append(f"v{v}")
            if is_my:
                sub_parts.append("Port 3306")
                if running and root_status in ("set", "blank"):
                    sub_parts.append("root password set" if root_status == "set" else "no root password")
            elif key.startswith("postgresql"):
                sub_parts.append("Port 5432")

            row = Adw.ActionRow(title=key.upper() if key in ("mysql", "mariadb") else key.title())
            row.set_subtitle(" · ".join(sub_parts) if sub_parts else "Default database engine")
            row.add_prefix(status_dot(running if installed else False))

            suffix = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6, valign=Gtk.Align.CENTER)

            if installed:
                suffix.append(pill("● Running", "bh-pill-on") if running else pill("● Stopped", "bh-pill-off"))
            else:
                suffix.append(pill("Not installed", "bh-pill-off"))

            if not installed:
                install_btn = Gtk.Button(
                    label="Install",
                    icon_name="list-add-symbolic",
                    css_classes=["suggested-action"],
                    valign=Gtk.Align.CENTER,
                )
                install_btn.connect(
                    "clicked",
                    lambda *_, k=key: self.win.run_progress(
                        ["install", k],
                        f"Installing {k}",
                        f"Downloading and setting up {k}…",
                        f"{k} installed.",
                    ),
                )
                suffix.append(install_btn)
            else:
                actions_group = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2, margin_start=4)

                verb = "stop" if running else "start"
                icon = "media-playback-stop-symbolic" if running else "media-playback-start-symbolic"
                toggle_b = Gtk.Button(
                    icon_name=icon,
                    tooltip_text=f"{verb.title()} {key}",
                    css_classes=["bh-quick-btn", "flat"],
                )
                toggle_b.connect(
                    "clicked",
                    lambda *_, k=key, v=verb: self.win.run_verb([v, k], f"{v.title()}ing {k}…"),
                )
                actions_group.append(toggle_b)

                restart_b = Gtk.Button(
                    icon_name="view-refresh-symbolic",
                    tooltip_text=f"Restart {key}",
                    css_classes=["bh-quick-btn", "flat"],
                )
                restart_b.connect(
                    "clicked",
                    lambda *_, k=key: self.win.run_verb(["restart", k], f"Restarting {key}…"),
                )
                actions_group.append(restart_b)

                if is_my and running:
                    pwd_b = Gtk.Button(
                        icon_name="dialog-password-symbolic",
                        tooltip_text="Set root password",
                        css_classes=["bh-quick-btn", "flat"],
                    )
                    pwd_b.connect("clicked", lambda *_: self.win.db_root_dialog())
                    actions_group.append(pwd_b)

                suffix.append(actions_group)

            row.add_suffix(suffix)
            listbox.append(row)

        self.servers_container.append(listbox)

    # ── Managed Databases Section ──
    def _render_dbs_section(self) -> None:
        child = self.dbs_container.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self.dbs_container.remove(child)
            child = nxt

        filtered_dbs = [d for d in self._last_dbs if self._matches_filter(d)]

        hdr_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        hdr_box.append(Gtk.Label(label="Managed Databases", xalign=0, css_classes=["title-4"]))
        if filtered_dbs:
            hdr_box.append(pill(f"{len(filtered_dbs)} databases", "bh-pill-blue"))
        hdr_box.append(Gtk.Box(hexpand=True))
        hdr_box.append(Gtk.Label(label=f"{len(filtered_dbs)} items", css_classes=["dim-label", "caption"]))
        self.dbs_container.append(hdr_box)

        listbox = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE, css_classes=["boxed-list"])

        for item in filtered_dbs:
            name = item.get("name", "")
            engine = item.get("engine", "mysql")
            is_pg = engine in ("pg", "postgresql")

            row = Adw.ActionRow(title=name)
            row.set_subtitle("PostgreSQL instance · Port 5432" if is_pg else "MariaDB / MySQL database · utf8mb4")

            # Check if engine is running
            db_svcs = [x for x in self._last_services if x.get("role") == "db"]
            eng_running = any(
                (s["key"].startswith("postgresql") if is_pg else s["key"] in ("mariadb", "mysql"))
                and s.get("running")
                for s in db_svcs
            )
            row.add_prefix(status_dot(eng_running))

            suffix = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6, valign=Gtk.Align.CENTER)
            suffix.append(pill("PostgreSQL", "bh-pill-blue") if is_pg else pill("MySQL", "bh-pill-blue"))

            actions_group = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2, margin_start=4)

            if not is_pg:
                pwd_b = Gtk.Button(
                    icon_name="dialog-password-symbolic",
                    tooltip_text="Change database user password",
                    css_classes=["bh-quick-btn", "flat"],
                )
                pwd_b.connect("clicked", lambda *_, n=name: self.win.db_password_dialog(n))
                actions_group.append(pwd_b)

            drop_b = Gtk.Button(
                icon_name="user-trash-symbolic",
                tooltip_text=f"Drop database {name}",
                css_classes=["bh-quick-btn", "flat", "destructive-action"],
            )
            drop_b.connect(
                "clicked",
                lambda *_, n=name, e=engine: self.win.confirm(
                    f"Drop database “{n}”?",
                    f"This will permanently drop the {n} database from {e}. This cannot be undone.",
                    lambda: self.win.db_drop(n, e),
                ),
            )
            actions_group.append(drop_b)

            suffix.append(actions_group)
            row.add_suffix(suffix)
            listbox.append(row)

        self.dbs_container.append(listbox)

        has_visible = len(filtered_dbs) > 0 or len(self._last_dbs) == 0
        self.dbs_container.set_visible(len(filtered_dbs) > 0)
        self.empty_page.set_visible(len(filtered_dbs) == 0 and len(self._last_dbs) > 0)

