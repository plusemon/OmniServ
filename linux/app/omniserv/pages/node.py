"""Node apps pane: fnm runtime management and managed Node.js application list."""
from __future__ import annotations

import os
import re

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk, Pango  # noqa: E402

from ..widgets import pill, status_dot, status_pill
from ._shared import (
    CardGrid,
    _open,
    _open_text_editor,
    _open_terminal,
    clean_version,
)

APP_FILTER_CHIPS = [
    ("all", "All"),
    ("running", "Running"),
    ("stopped", "Stopped"),
]


class _AppsPage(Gtk.Box):
    """Shared base for Node + Python panes with modern flat dashboard layout."""
    KIND = "node"
    TITLE = "Node.js Applications"
    SUBTITLE_DESC = "Node.js applications and runtime"

    def __init__(self, win) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.win = win
        self._current_filter = "all"
        self._search_query = ""
        self._last_apps: list[dict] = []
        self._last_services: list[dict] = []
        self._sig = None
        self._rt_handler = None

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
        tb.append(Gtk.Label(label=self.TITLE, xalign=0, css_classes=["title-1"]))
        self.subtitle = Gtk.Label(
            label=f"Manage {self.SUBTITLE_DESC}, processes, and reverse proxy routes",
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

        self.rt_action_btn = Gtk.Button(valign=Gtk.Align.CENTER, visible=False)
        btn_group.append(self.rt_action_btn)

        self.add_app_btn = Gtk.Button(
            label=f"Add {self.KIND} app",
            icon_name="list-add-symbolic",
            css_classes=["suggested-action"],
            valign=Gtk.Align.CENTER,
        )
        self.add_app_btn.connect(
            "clicked", lambda *_: self.win.add_site_dialog(default_type=self.KIND)
        )
        btn_group.append(self.add_app_btn)

        head.append(btn_group)
        self.body.append(head)

        # ── 2. Top Summary Metric Cards (CardGrid) ──
        cards = CardGrid()
        self.c_rt = self._metric_card("Runtime Version")
        self.c_apps = self._metric_card("Applications")
        self.c_pm = self._metric_card("Environment")
        self.c_proxy = self._metric_card("Gateway")
        for c in (
            self.c_rt["card"],
            self.c_apps["card"],
            self.c_pm["card"],
            self.c_proxy["card"],
        ):
            cards.add_card(c)
        self.body.append(cards)

        # ── 3. Runtime Environment Section ──
        self.rt_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.body.append(self.rt_container)

        # ── 4. Inline Search & Category Filter Toolbar ──
        filter_bar = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=10,
            valign=Gtk.Align.CENTER,
        )

        self.search_entry = Gtk.SearchEntry(
            placeholder_text=f"Search {self.KIND} apps (e.g. name, port, command)…",
        )
        self.search_entry.set_size_request(280, -1)
        self.search_entry.connect("search-changed", self._on_search_changed)
        filter_bar.append(self.search_entry)

        # Filter Chips
        self.chips_row = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL, spacing=6
        )
        self._chip_buttons: dict[str, Gtk.ToggleButton] = {}
        for f_key, f_label in APP_FILTER_CHIPS:
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

        # ── 5. Managed Apps Section ──
        self.apps_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.body.append(self.apps_container)

        # Empty status page
        self.empty_page = Adw.StatusPage(
            icon_name="system-search-symbolic",
            title=f"No matching {self.KIND} applications",
            description=f"Try clearing your search query or clicking “Add {self.KIND} app”.",
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
        self._render_apps_section()

    def _on_chip_toggled(self, key: str, button: Gtk.ToggleButton) -> None:
        if not button.get_active():
            if self._current_filter == key:
                button.set_active(True)
            return

        self._current_filter = key
        for k, b in self._chip_buttons.items():
            if k != key and b.get_active():
                b.set_active(False)
        self._render_apps_section()

    def _matches_filter(self, a: dict) -> bool:
        if self._search_query:
            q = self._search_query
            name = a.get("name", "").lower()
            raw = a.get("raw", "").lower()
            if not (q in name or q in raw):
                return False

        f = self._current_filter
        if f == "all":
            return True
        elif f == "running":
            return bool(a.get("running"))
        elif f == "stopped":
            return not bool(a.get("running"))
        return True

    def _apps(self) -> list[dict]:
        rc, out = self.win.engine.run(f"{self.KIND}site", "list")
        apps = []
        for line in out.splitlines():
            line = line.strip()
            low = line.lower()
            if (
                not line
                or "<" in line
                or "omniserv" in low
                or low.startswith("no ")
                or "—" in line
                or "usage" in low
                or ".test" in line
                or len(line) <= 1
            ):
                continue
            m = re.search(r"([a-z0-9][a-z0-9._-]*)", line, re.I)
            if m and m.group(1) not in ("python", "node", "site", "app"):
                running = "running" in low or "active" in low or "pid" in low or "up" in low
                port_match = re.search(r":(\d{2,5})", line)
                port = port_match.group(1) if port_match else ""
                apps.append(
                    {
                        "name": m.group(1),
                        "line": GLib.markup_escape_text(line),
                        "raw": line,
                        "running": running,
                        "port": port,
                    }
                )
        return apps

    def _set_runtime_btn(self, label: str | None, handler=None) -> None:
        if not label:
            self.rt_action_btn.set_visible(False)
            return
        self.rt_action_btn.set_label(label)
        self._rt_handler = handler
        self.rt_action_btn.set_visible(True)
        # Clear previous connections and reconnect
        try:
            self.rt_action_btn.disconnect_by_func(self._on_rt_action_clicked)
        except Exception:
            pass
        self.rt_action_btn.connect("clicked", self._on_rt_action_clicked)

    def _on_rt_action_clicked(self, *_) -> None:
        if self._rt_handler:
            self._rt_handler()

    def refresh(self, data: dict) -> None:
        services = data.get("services", [])
        self._last_services = services
        self._last_apps = self._apps()

        self._update_metrics(data)
        self._update_chip_labels(self._last_apps)

        self._render_runtime_section(data)
        self._render_apps_section()

    def _update_chip_labels(self, apps: list[dict]) -> None:
        counts = {
            "all": len(apps),
            "running": sum(1 for a in apps if a.get("running")),
            "stopped": sum(1 for a in apps if not a.get("running")),
        }
        for k, btn in self._chip_buttons.items():
            base_label = next(lbl for key, lbl in APP_FILTER_CHIPS if key == k)
            count = counts.get(k, 0)
            btn.set_label(f"{base_label} ({count})")

    def _render_runtime_section(self, data: dict) -> None:
        # Implemented by subclass
        pass

    def _update_metrics(self, data: dict) -> None:
        # Implemented by subclass
        pass

    # ── Applications List Rendering ──
    def _render_apps_section(self) -> None:
        child = self.apps_container.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self.apps_container.remove(child)
            child = nxt

        filtered = [a for a in self._last_apps if self._matches_filter(a)]

        hdr_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        hdr_box.append(Gtk.Label(label="Managed Applications", xalign=0, css_classes=["title-4"]))
        running_cnt = sum(1 for a in filtered if a.get("running"))
        if running_cnt > 0:
            hdr_box.append(pill(f"{running_cnt} active", "bh-pill-on"))
        hdr_box.append(Gtk.Box(hexpand=True))
        hdr_box.append(
            Gtk.Label(
                label=f"{len(filtered)} app{'s' if len(filtered) != 1 else ''}",
                css_classes=["dim-label", "caption"],
            )
        )
        self.apps_container.append(hdr_box)

        listbox = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE, css_classes=["boxed-list"])

        for a in filtered:
            name = a["name"]
            running = a.get("running", False)
            port = a.get("port", "")

            row = Adw.ActionRow(title=name)
            sub = a.get("raw", "") or f"{self.KIND.title()} supervised process"
            row.set_subtitle(sub)
            row.add_prefix(status_dot(running))

            suffix = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6, valign=Gtk.Align.CENTER)

            if running:
                suffix.append(pill("● Running", "bh-pill-on"))
            else:
                suffix.append(pill("● Stopped", "bh-pill-off"))

            if port:
                suffix.append(pill(f"Port {port}", "bh-pill-blue"))

            actions_group = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2, margin_start=4)

            # Start / Stop / Restart
            verb = "stop" if running else "start"
            icon = "media-playback-stop-symbolic" if running else "media-playback-start-symbolic"
            toggle_b = Gtk.Button(
                icon_name=icon,
                tooltip_text=f"{verb.title()} {name}",
                css_classes=["bh-quick-btn", "flat"],
            )
            toggle_b.connect(
                "clicked",
                lambda *_, n=name, v=verb: self.win.run_verb([f"{self.KIND}site", v, n], f"{v.title()}ing {n}…"),
            )
            actions_group.append(toggle_b)

            restart_b = Gtk.Button(
                icon_name="view-refresh-symbolic",
                tooltip_text=f"Restart {name}",
                css_classes=["bh-quick-btn", "flat"],
            )
            restart_b.connect(
                "clicked",
                lambda *_, n=name: self.win.run_verb([f"{self.KIND}site", "restart", n], f"Restarting {n}…"),
            )
            actions_group.append(restart_b)

            # Remove app
            rm_b = Gtk.Button(
                icon_name="user-trash-symbolic",
                tooltip_text=f"Remove {name}",
                css_classes=["bh-quick-btn", "flat", "destructive-action"],
            )
            rm_b.connect(
                "clicked",
                lambda *_, n=name: self.win.confirm(
                    f"Remove application “{n}”?",
                    f"Removes the {self.KIND} application definition and process supervisor.",
                    lambda: self.win.run_verb([f"{self.KIND}site", "rm", n], f"Removing {n}…"),
                ),
            )
            actions_group.append(rm_b)

            suffix.append(actions_group)
            row.add_suffix(suffix)
            listbox.append(row)

        self.apps_container.append(listbox)

        has_visible = len(filtered) > 0 or len(self._last_apps) == 0
        self.apps_container.set_visible(len(filtered) > 0)
        self.empty_page.set_visible(len(filtered) == 0 and len(self._last_apps) > 0)


class NodePage(_AppsPage):
    KIND, TITLE = "node", "Node.js Applications"
    SUBTITLE_DESC = "Node.js applications and runtime"

    def _update_metrics(self, data: dict) -> None:
        installed = any(s["key"] == "fnm" and s["installed"] for s in data.get("services", []))
        out = self.win.engine.run("node", "list")[1].strip() if installed else ""

        total_apps = len(self._last_apps)
        running_apps = sum(1 for a in self._last_apps if a.get("running"))

        # 1. Runtime Version
        if installed and out:
            cur_ver = clean_version(out)
            self.c_rt["val"].set_label(f"Node v{cur_ver}" if cur_ver else "Node Active")
            self.c_rt["sub"].set_label("fnm Fast Node Manager")
            self._set_card_badge(self.c_rt["badge"], "● Active", "bh-pill-on")
        elif installed:
            self.c_rt["val"].set_label("fnm Ready")
            self.c_rt["sub"].set_label("No Node version selected")
            self._set_card_badge(self.c_rt["badge"], "● Installed", "bh-pill-blue")
        else:
            self.c_rt["val"].set_label("Not Installed")
            self.c_rt["sub"].set_label("fnm runtime manager")
            self._set_card_badge(self.c_rt["badge"], "● Inactive", "bh-pill-off")

        # 2. Total Applications
        self.c_apps["val"].set_label(f"{total_apps} Apps" if total_apps != 1 else "1 App")
        self.c_apps["sub"].set_label(f"{running_apps} active Node processes")
        self._set_card_badge(
            self.c_apps["badge"],
            "● Live" if running_apps > 0 else ("● Idle" if total_apps > 0 else "● Empty"),
            "bh-pill-on" if running_apps > 0 else "bh-pill-off",
        )

        # 3. Environment / Package Manager
        self.c_pm["val"].set_label("npm / pnpm / yarn")
        self.c_pm["sub"].set_label("Node package ecosystem")
        self._set_card_badge(self.c_pm["badge"], "● Ready" if installed else "● Offline", "bh-pill-blue" if installed else "bh-pill-off")

        # 4. Reverse Proxy Gateway
        self.c_proxy["val"].set_label("Nginx Gateway")
        self.c_proxy["sub"].set_label("Reverse proxy to internal ports")
        self._set_card_badge(self.c_proxy["badge"], "● Live", "bh-pill-on")

        self.subtitle.set_label(
            f"{total_apps} applications · {running_apps} active processes · fnm Fast Node Manager"
        )

    def _render_runtime_section(self, data: dict) -> None:
        child = self.rt_container.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self.rt_container.remove(child)
            child = nxt

        installed = any(s["key"] == "fnm" and s["installed"] for s in data.get("services", []))
        out = self.win.engine.run("node", "list")[1].strip() if installed else ""

        hdr_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        hdr_box.append(Gtk.Label(label="Runtime & Version Manager", xalign=0, css_classes=["title-4"]))
        if installed:
            hdr_box.append(pill("fnm active", "bh-pill-on"))
        self.rt_container.append(hdr_box)

        listbox = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE, css_classes=["boxed-list"])
        row = Adw.ActionRow(title="Node.js (fnm Fast Node Manager)" if installed else "Node.js — fnm Not Installed")
        row.set_subtitle((out[:80] if out else "Install a Node version to run Node apps") if installed else "Install fnm, then a Node version, to run Node applications")
        row.add_prefix(status_dot(installed))

        suffix = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6, valign=Gtk.Align.CENTER)

        if installed:
            inst_ver_btn = Gtk.Button(
                label="Install Node version…",
                icon_name="software-update-available-symbolic",
                valign=Gtk.Align.CENTER,
            )
            inst_ver_btn.connect("clicked", lambda *_: self._install_node())
            suffix.append(inst_ver_btn)
            self._set_runtime_btn("Install Node version…", self._install_node)
        else:
            inst_fnm_btn = Gtk.Button(
                label="Install fnm",
                icon_name="list-add-symbolic",
                css_classes=["suggested-action"],
                valign=Gtk.Align.CENTER,
            )
            inst_fnm_btn.connect(
                "clicked",
                lambda *_: self.win.run_progress(
                    ["install", "fnm"],
                    "Installing fnm",
                    "Downloading and configuring Fast Node Manager…",
                    "fnm installed.",
                ),
            )
            suffix.append(inst_fnm_btn)
            self._set_runtime_btn(
                "Install fnm",
                lambda: self.win.run_progress(
                    ["install", "fnm"],
                    "Installing fnm",
                    "Downloading the Node version manager…",
                    "fnm installed.",
                ),
            )

        row.add_suffix(suffix)
        listbox.append(row)
        self.rt_container.append(listbox)

    def _install_node(self) -> None:
        self.win.choose(
            "Install Node",
            "Pick a version to install and set as default:",
            ["22", "20", "18"],
            lambda v: self.win.run_verb(
                ["node", "install", v],
                f"Installing Node {v}…",
                then=(["node", "use", v], f"Setting Node {v} as default…"),
            ),
        )
