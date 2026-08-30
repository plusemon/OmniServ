"""Dashboard pane: Start/Stop/Restart-all, status cards, system metrics sparkline,
websites panel, web-tools toggles, and activity log.
"""
from __future__ import annotations

from collections import deque

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import GLib, Gtk, Pango  # noqa: E402

from ..metrics import CpuSampler, NetSampler, disk, memory, rate_str
from ..widgets import PagedList, pill, status_dot
from ._shared import (
    _HAVE_CAIRO,
    CardGrid,
    _open,
    _set_badge,
    _set_dot,
    build_site_row,
    is_tool,
    site_match,
)


class DashboardPage(Gtk.Box):
    """Parity with the macOS/Windows dashboard: Start/Stop/Restart-all, status cards
    (Web/PHP/DB/Cache), CPU sparkline + Memory/Disk/Network, the websites panel, the
    web-tools toggles, and an activity console drawer."""

    def __init__(self, win) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.win = win
        self.cpu = CpuSampler()
        self.net = NetSampler()
        self.cpu_hist: deque = deque(maxlen=40)
        self.net_hist: deque = deque(maxlen=40)
        self._loading_tools = False
        self._last_log_len = 0

        scroller = Gtk.ScrolledWindow(vexpand=True, hexpand=True)
        # NEVER horizontal-scroll: otherwise the ScrolledWindow lets the content keep its wide
        # natural width and just adds an h-scrollbar, so the cards never receive the narrowed
        # width and never reflow. NEVER forces the page width down onto the content.
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18,
                       margin_top=18, margin_bottom=18, margin_start=18, margin_end=18)
        scroller.set_child(body)
        self.append(scroller)

        # ── 6. Header: title + subtitle + segmented master control buttons ──
        head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        tb = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
        tb.append(Gtk.Label(label="Dashboard", xalign=0, css_classes=["title-1"]))
        self.subtitle = Gtk.Label(label="", xalign=0, css_classes=["dim-label"])
        tb.append(self.subtitle)
        head.append(tb)

        btn_group = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, css_classes=["bh-button-group", "linked"],
                            valign=Gtk.Align.CENTER)
        self.start_btn = Gtk.Button(label="Start all", icon_name="media-playback-start-symbolic")
        self.start_btn.connect("clicked", lambda *_: self.win.run_verb(["start", "all"], "Starting all services…"))
        self.stop_btn = Gtk.Button(label="Stop all", icon_name="media-playback-stop-symbolic")
        self.stop_btn.connect("clicked", lambda *_: self.win.run_verb(["stop", "all"], "Stopping all services…"))
        self.restart_btn = Gtk.Button(label="Restart", icon_name="view-refresh-symbolic")
        self.restart_btn.connect("clicked", lambda *_: self.win.run_verb(["restart", "all"], "Restarting all services…"))
        for b in (self.start_btn, self.stop_btn, self.restart_btn):
            btn_group.append(b)
        head.append(btn_group)
        body.append(head)

        # ── 1 & 2. 8 cards in ONE responsive grid: Web/PHP/DB/Cache + CPU/Mem/Storage/Net ──
        cards = CardGrid()
        self.c_web = self._status_card("Web Server")
        self.c_php = self._status_card("PHP")
        self.c_db = self._status_card("Database")
        self.c_cache = self._status_card("Cache")
        self.cpu_card = self._cpu_card()
        self.mem = self._bar_card("Memory")
        self.disk = self._bar_card("Storage")
        self.net_card = self._net_card()
        for c in (self.c_web["card"], self.c_php["card"], self.c_db["card"], self.c_cache["card"],
                  self.cpu_card["card"], self.mem["card"], self.disk["card"], self.net_card["card"]):
            cards.add_card(c)
        body.append(cards)

        # ── 3. Websites panel with + New Site action ──
        self.web_header = Gtk.Label(label="Websites", xalign=0, css_classes=["title-4"])
        body.append(self.web_header)

        new_site_btn = Gtk.Button(label="New Site", icon_name="list-add-symbolic",
                                  css_classes=["suggested-action"], valign=Gtk.Align.CENTER)
        new_site_btn.connect("clicked", lambda *_: self.win.add_site_dialog())

        self.site_list = PagedList(lambda s: build_site_row(self.win, s), site_match,
                                   page_size=self.win.cfg_int("dashboard_page_size", 5),
                                   empty_text="No sites yet — add one with the '+ New Site' button.",
                                   on_page_size_changed=lambda n: self.win.set_cfg("dashboard_page_size", n),
                                   scroll=False,
                                   extra_action=new_site_btn)
        body.append(self.site_list)

        # ── 4. Web tools ──
        body.append(Gtk.Label(label="Web tools", xalign=0, css_classes=["title-4"]))
        tools = CardGrid()
        self.t_pma = self._tool_card("phpMyAdmin", "phpmyadmin", ["pma", "install"])
        self.t_adm = self._tool_card("Adminer", "adminer", ["adminer", "install"])
        self.t_mail = self._tool_card("Mailpit", "mailpit", ["mailpit", "setup"])
        for t in (self.t_pma, self.t_adm, self.t_mail):
            tools.add_card(t["card"])
        body.append(tools)

        # ── 5. Collapsible Activity Console Dock ──
        self._build_activity_console(body)

    # ── card builders ──
    def _status_card(self, title: str) -> dict:
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, css_classes=["card", "bh-metric"])
        top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        top.append(Gtk.Label(label=title, xalign=0, hexpand=True, css_classes=["bh-metric-cap", "dim-label"]))
        badge = pill("● Stopped", "bh-pill-off")
        top.append(badge)
        card.append(top)

        val = Gtk.Label(label="—", xalign=0, css_classes=["bh-metric-val"], wrap=True,
                        wrap_mode=Pango.WrapMode.WORD_CHAR, max_width_chars=18)
        sub = Gtk.Label(label="", xalign=0, css_classes=["dim-label", "caption"])
        card.append(val)
        card.append(sub)
        return {"card": card, "val": val, "sub": sub, "badge": badge}

    def _cpu_card(self) -> dict:
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, css_classes=["card", "bh-metric"])
        top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        top.append(Gtk.Label(label="CPU", xalign=0, hexpand=True, css_classes=["bh-metric-cap", "dim-label"]))
        badge = pill("0%", "bh-pill-blue")
        top.append(badge)
        card.append(top)

        val = Gtk.Label(label="0%", xalign=0, css_classes=["bh-metric-val"])
        card.append(val)
        self.spark = Gtk.DrawingArea(content_height=36, hexpand=True)
        if _HAVE_CAIRO:
            self.spark.set_draw_func(self._draw_cpu_spark)
        card.append(self.spark)
        return {"card": card, "val": val, "badge": badge}

    def _bar_card(self, title: str) -> dict:
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, css_classes=["card", "bh-metric"])
        top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        top.append(Gtk.Label(label=title, xalign=0, hexpand=True, css_classes=["bh-metric-cap", "dim-label"]))
        badge = pill("0%", "bh-pill-blue")
        top.append(badge)
        card.append(top)

        val = Gtk.Label(label="—", xalign=0, css_classes=["bh-metric-val"])
        card.append(val)
        bar = Gtk.ProgressBar()
        card.append(bar)
        sub = Gtk.Label(label="", xalign=0, css_classes=["dim-label", "caption"])
        card.append(sub)
        return {"card": card, "val": val, "bar": bar, "badge": badge, "sub": sub}

    def _net_card(self) -> dict:
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, css_classes=["card", "bh-metric"])
        top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        top.append(Gtk.Label(label="Network", xalign=0, hexpand=True, css_classes=["bh-metric-cap", "dim-label"]))
        badge = pill("Live", "bh-pill-on")
        top.append(badge)
        card.append(top)

        val = Gtk.Label(label="↓ 0 KB/s  ↑ 0 KB/s", xalign=0, css_classes=["bh-metric-val"])
        card.append(val)
        self.net_spark = Gtk.DrawingArea(content_height=36, hexpand=True)
        if _HAVE_CAIRO:
            self.net_spark.set_draw_func(self._draw_net_spark)
        card.append(self.net_spark)
        return {"card": card, "val": val, "badge": badge}

    def _tool_card(self, title: str, site_name: str, on_verb: list[str]) -> dict:
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, css_classes=["card", "bh-metric"])
        top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        top.append(Gtk.Label(label=title, xalign=0, hexpand=True, css_classes=["bh-metric-cap"]))
        badge = pill("● Stopped", "bh-pill-off")
        top.append(badge)
        card.append(top)

        sub = Gtk.Label(label="Not active", xalign=0, css_classes=["dim-label", "caption"])
        card.append(sub)

        bottom = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8, margin_top=4)
        sw = Gtk.Switch(valign=Gtk.Align.CENTER)
        sw.connect("notify::active", lambda s, _p, n=site_name, v=on_verb: self._tool_toggled(n, v, s.get_active()))
        bottom.append(sw)
        bottom.append(Gtk.Label(label="", hexpand=True))
        openb = Gtk.Button(label="Open", valign=Gtk.Align.CENTER, sensitive=False)
        openb.connect("clicked", lambda *_, t=site_name: self._tool_open(t))
        bottom.append(openb)
        card.append(bottom)
        return {"card": card, "switch": sw, "badge": badge, "sub": sub, "open": openb, "url": ""}

    # ── Activity Console Dock ──
    def _build_activity_console(self, body: Gtk.Box) -> None:
        dock = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, css_classes=["bh-console-dock"])

        # Console Header Bar
        hdr = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8, css_classes=["bh-console-header"])
        hdr.append(Gtk.Image.new_from_icon_name("utilities-terminal-symbolic"))
        hdr.append(Gtk.Label(label="Activity Console", css_classes=["heading"]))
        hdr.append(status_dot(True))
        self.log_count_pill = pill("0 events", "bh-pill-off")
        hdr.append(self.log_count_pill)
        hdr.append(Gtk.Box(hexpand=True))

        copy_b = Gtk.Button(icon_name="edit-copy-symbolic", tooltip_text="Copy console output",
                            css_classes=["bh-quick-btn", "flat"])
        copy_b.connect("clicked", lambda *_: self._copy_log())
        hdr.append(copy_b)

        clear_b = Gtk.Button(icon_name="edit-clear-symbolic", tooltip_text="Clear console",
                             css_classes=["bh-quick-btn", "flat"])
        clear_b.connect("clicked", lambda *_: self._clear_log())
        hdr.append(clear_b)

        toggle_b = Gtk.Button(icon_name="pan-down-symbolic", tooltip_text="Collapse/Expand console",
                              css_classes=["bh-quick-btn", "flat"])
        hdr.append(toggle_b)

        # Revealer for collapse/expand
        revealer = Gtk.Revealer(reveal_child=True, transition_type=Gtk.RevealerTransitionType.SLIDE_DOWN)
        def on_toggle(*_):
            active = not revealer.get_reveal_child()
            revealer.set_reveal_child(active)
            toggle_b.set_icon_name("pan-down-symbolic" if active else "pan-up-symbolic")
        toggle_b.connect("clicked", on_toggle)

        # TextView inside ScrolledWindow
        self.log_view = Gtk.TextView(editable=False, monospace=True, css_classes=["bh-console-body"])
        buf = self.log_view.get_buffer()
        self.tag_time = buf.create_tag("time", foreground="#6b7280", scale=0.9)
        self.tag_ok = buf.create_tag("ok", foreground="#2ec27e", weight=Pango.Weight.BOLD.value_nick)
        self.tag_err = buf.create_tag("err", foreground="#f87171", weight=Pango.Weight.BOLD.value_nick)
        self.tag_warn = buf.create_tag("warn", foreground="#f59e0b", weight=Pango.Weight.BOLD.value_nick)
        self.tag_normal = buf.create_tag("normal", foreground="#e4e7eb")

        log_sc = Gtk.ScrolledWindow(min_content_height=140, max_content_height=260)
        log_sc.set_child(self.log_view)
        revealer.set_child(log_sc)

        dock.append(hdr)
        dock.append(revealer)
        body.append(dock)

    def _copy_log(self) -> None:
        buf = self.log_view.get_buffer()
        text = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False)
        if text:
            self.win._copy(text)
            self.win.toast("Console log copied to clipboard")

    def _clear_log(self) -> None:
        if hasattr(self.win, "applog"):
            self.win.applog.clear()
        self.log_view.get_buffer().set_text("")
        self._last_log_len = 0
        self.log_count_pill.set_label("0 events")

    # ── drawing ──
    def _draw_cpu_spark(self, area, cr, w, h):
        pts = list(self.cpu_hist)
        if len(pts) < 2:
            return

        # Background subtle grid lines
        cr.set_source_rgba(1.0, 1.0, 1.0, 0.06)
        cr.set_line_width(1)
        for frac in (0.33, 0.66):
            y_grid = h * frac
            cr.move_to(0, y_grid)
            cr.line_to(w, y_grid)
            cr.stroke()

        # Area fill
        n = len(pts)
        cr.move_to(0, h)
        for i, v in enumerate(pts):
            x = i * w / (n - 1)
            y = h - (v / 100.0) * (h - 4) - 2
            cr.line_to(x, y)
        cr.line_to(w, h)
        cr.close_path()
        cr.set_source_rgba(0.051, 0.431, 0.992, 0.18)
        cr.fill()

        # Line stroke
        for i, v in enumerate(pts):
            x = i * w / (n - 1)
            y = h - (v / 100.0) * (h - 4) - 2
            if i == 0:
                cr.move_to(x, y)
            else:
                cr.line_to(x, y)
        cr.set_source_rgb(0.051, 0.431, 0.992)
        cr.set_line_width(2.0)
        cr.stroke()

    def _draw_net_spark(self, area, cr, w, h):
        pts = list(self.net_hist)
        if len(pts) < 2:
            return

        # Background subtle grid lines
        cr.set_source_rgba(1.0, 1.0, 1.0, 0.06)
        cr.set_line_width(1)
        for frac in (0.33, 0.66):
            y_grid = h * frac
            cr.move_to(0, y_grid)
            cr.line_to(w, y_grid)
            cr.stroke()

        # Normalize with minimum scale of 100 KB/s
        max_rate = max(max(pts, default=1.0), 100.0)
        n = len(pts)
        cr.move_to(0, h)
        for i, v in enumerate(pts):
            x = i * w / (n - 1)
            y = h - (min(v, max_rate) / max_rate) * (h - 4) - 2
            cr.line_to(x, y)
        cr.line_to(w, h)
        cr.close_path()
        cr.set_source_rgba(0.18, 0.76, 0.49, 0.18)
        cr.fill()

        # Line stroke
        for i, v in enumerate(pts):
            x = i * w / (n - 1)
            y = h - (min(v, max_rate) / max_rate) * (h - 4) - 2
            if i == 0:
                cr.move_to(x, y)
            else:
                cr.line_to(x, y)
        cr.set_source_rgb(0.18, 0.76, 0.49)
        cr.set_line_width(2.0)
        cr.stroke()

    # ── web tools ──
    def _tool_toggled(self, name, on_verb, on):
        if self._loading_tools:
            return
        args = on_verb if on else ["site", "rm", name]
        self.win.run_verb(args, f"{'Enabling' if on else 'Disabling'} {name}…")

    def _tool_open(self, name):
        t = {"phpmyadmin": self.t_pma, "adminer": self.t_adm, "mailpit": self.t_mail}[name]
        if t["url"]:
            _open(t["url"])

    def _set_tool(self, t, sites_all, name):
        site = next((s for s in sites_all if s["name"].lower() == name), None)
        active = bool(site and site.get("enabled", True))
        t["switch"].set_active(active)
        t["open"].set_sensitive(active)
        if active:
            t["open"].add_css_class("suggested-action")
            secure = bool(site and site.get("secure"))
            url = (("https://" if secure else "http://") + site["domain"]) if site else ""
            _set_badge(t["badge"], "● Running", "bh-pill-on")
            t["sub"].set_label(f"Active · {site['domain']}")
            t["url"] = url
        else:
            t["open"].remove_css_class("suggested-action")
            _set_badge(t["badge"], "● Stopped", "bh-pill-off")
            t["sub"].set_label("Not active")
            t["url"] = ""

    # ── refresh ──
    def refresh(self, data: dict) -> None:
        services = data.get("services", [])
        all_sites = data.get("sites", [])
        run = lambda k: any(s["key"] == k and s.get("running") for s in services)  # noqa: E731

        php_vers = sorted([s["key"][4:] for s in services
                           if s["role"] == "php" and s["key"].startswith("php@") and s["installed"]], reverse=True)
        sites = sorted([s for s in all_sites if not is_tool(s["name"])], key=lambda s: s["name"])

        nginx, apache = run("nginx"), run("httpd")
        web = "nginx + apache" if (nginx and apache) else "nginx" if nginx else "apache" if apache else "nginx"
        self._fill(self.c_web, web, f"{len(sites)} site{'' if len(sites) == 1 else 's'}", nginx or apache)
        self._fill(self.c_php, ", ".join(php_vers) if php_vers else "not installed",
                   f"{len(php_vers)} installed", any(s["role"] == "php" and s.get("running") for s in services),
                   missing=not php_vers)
        maria, my, pg = run("mariadb"), run("mysql"), run("postgresql@16") or run("postgresql")
        dbrun = maria or my or pg
        self._fill(self.c_db, "MariaDB" if maria else "MySQL" if my else "PostgreSQL" if pg else "MySQL / MariaDB",
                   "running" if dbrun else "stopped", dbrun)
        redis, memc = run("redis"), run("memcached")
        self._fill(self.c_cache, "Redis · Memcached",
                   f"redis {'on' if redis else 'off'}, memcached {'on' if memc else 'off'}", redis or memc)

        self.subtitle.set_label(f"{sum(1 for s in services if s.get('running'))} services running · {len(sites)} sites")

        # CPU
        cpu = self.cpu.percent()
        self.cpu_card["val"].set_label(f"{cpu:.0f}%")
        self.cpu_card["badge"].set_label(f"{cpu:.0f}%")
        self.cpu_hist.append(cpu)
        if _HAVE_CAIRO:
            self.spark.queue_draw()

        # Memory
        mu, mt, mp = memory()
        self.mem["val"].set_label(f"{mu:.1f} / {mt:.1f} GB")
        self.mem["bar"].set_fraction(min(1.0, mp / 100))
        self.mem["badge"].set_label(f"{mp:.0f}%")
        self.mem["sub"].set_label(f"{max(0.0, mt - mu):.1f} GB free")

        # Storage
        du, dt, dp = disk()
        self.disk["val"].set_label(f"{du:.0f} / {dt:.0f} GB")
        self.disk["bar"].set_fraction(min(1.0, dp / 100))
        self.disk["badge"].set_label(f"{dp:.0f}%")
        self.disk["sub"].set_label(f"{max(0.0, dt - du):.0f} GB free")

        # Network
        down, up = self.net.rate_kbps()
        self.net_card["val"].set_label(f"↓ {rate_str(down)}  ↑ {rate_str(up)}")
        self.net_hist.append(down + up)
        if _HAVE_CAIRO:
            self.net_spark.queue_draw()

        # Master Controls
        daemons = {"nginx", "httpd", "mariadb", "postgresql@16", "redis", "memcached", "mailpit"}
        any_running = any(s.get("running") for s in services)
        to_start = any(s["key"] in daemons and s["installed"] and s.get("enabled") and not s.get("running")
                       for s in services)
        self.start_btn.set_sensitive(to_start)
        self.stop_btn.set_sensitive(any_running)
        self.restart_btn.set_sensitive(any_running)
        for b in (self.start_btn, self.stop_btn):
            b.remove_css_class("suggested-action")
        if to_start:
            self.start_btn.add_css_class("suggested-action")
        elif any_running:
            self.stop_btn.add_css_class("suggested-action")

        self.web_header.set_label(f"Websites ({len(sites)})")
        self.site_list.set_items(sites)

        self._loading_tools = True
        self._set_tool(self.t_pma, all_sites, "phpmyadmin")
        self._set_tool(self.t_adm, all_sites, "adminer")
        self._set_tool(self.t_mail, all_sites, "mailpit")
        self._loading_tools = False

        # Activity Console update with syntax colors
        log_entries = getattr(self.win, "applog", [])
        if len(log_entries) != self._last_log_len:
            self._last_log_len = len(log_entries)
            self._render_log_buffer(log_entries[-200:])
            self.log_count_pill.set_label(f"{len(log_entries)} events")

    def _render_log_buffer(self, log_lines: list[str]) -> None:
        buf = self.log_view.get_buffer()
        buf.set_text("")
        for line in log_lines:
            line_str = line.strip()
            if not line_str:
                continue
            if line_str.startswith("[") and "]" in line_str:
                time_part, _, rest = line_str.partition("]")
                buf.insert_with_tags(buf.get_end_iter(), time_part + "] ", self.tag_time)
                msg = rest.strip()
            else:
                msg = line_str

            if msg.startswith("✓") or "done" in msg.lower() or "success" in msg.lower():
                buf.insert_with_tags(buf.get_end_iter(), msg + "\n", self.tag_ok)
            elif msg.startswith("✗") or "failed" in msg.lower() or "error" in msg.lower():
                buf.insert_with_tags(buf.get_end_iter(), msg + "\n", self.tag_err)
            elif msg.startswith("!") or "warn" in msg.lower():
                buf.insert_with_tags(buf.get_end_iter(), msg + "\n", self.tag_warn)
            else:
                buf.insert_with_tags(buf.get_end_iter(), msg + "\n", self.tag_normal)

        # Auto-scroll to bottom
        mark = buf.create_mark(None, buf.get_end_iter(), False)
        self.log_view.scroll_to_mark(mark, 0.0, True, 0.0, 1.0)

    def _fill(self, card: dict, val: str, sub: str, on: bool, missing: bool = False) -> None:
        card["val"].set_label(val)
        card["sub"].set_label(sub)
        if missing:
            _set_badge(card["badge"], "● Not installed", "bh-pill-warn")
        elif on:
            _set_badge(card["badge"], "● Running", "bh-pill-on")
        else:
            _set_badge(card["badge"], "● Stopped", "bh-pill-off")
