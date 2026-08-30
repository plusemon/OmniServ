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
from ..widgets import PagedList, status_dot
from ._shared import (
    _HAVE_CAIRO,
    CardGrid,
    _open,
    _set_dot,
    build_site_row,
    is_tool,
    site_match,
)


class DashboardPage(Gtk.Box):
    """Parity with the macOS/Windows dashboard: Start/Stop/Restart-all, status cards
    (Web/PHP/DB/Cache), CPU sparkline + Memory/Disk/Network, the websites panel, the
    web-tools toggles, and an activity log."""

    def __init__(self, win) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.win = win
        self.cpu = CpuSampler()
        self.net = NetSampler()
        self.cpu_hist: deque = deque(maxlen=40)
        self._loading_tools = False

        scroller = Gtk.ScrolledWindow(vexpand=True, hexpand=True)
        # NEVER horizontal-scroll: otherwise the ScrolledWindow lets the content keep its wide
        # natural width and just adds an h-scrollbar, so the cards never receive the narrowed
        # width and never reflow. NEVER forces the page width down onto the content.
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16,
                       margin_top=18, margin_bottom=18, margin_start=18, margin_end=18)
        scroller.set_child(body)
        self.append(scroller)

        # ── header: title + subtitle + global buttons ──
        head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        tb = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
        tb.append(Gtk.Label(label="Dashboard", xalign=0, css_classes=["title-1"]))
        self.subtitle = Gtk.Label(label="", xalign=0, css_classes=["dim-label"])
        tb.append(self.subtitle)
        head.append(tb)
        self.start_btn = Gtk.Button(label="Start all", icon_name="media-playback-start-symbolic", valign=Gtk.Align.CENTER)
        self.start_btn.connect("clicked", lambda *_: self.win.run_verb(["start", "all"], "Starting all services…"))
        self.stop_btn = Gtk.Button(label="Stop all", icon_name="media-playback-stop-symbolic", valign=Gtk.Align.CENTER)
        self.stop_btn.connect("clicked", lambda *_: self.win.run_verb(["stop", "all"], "Stopping all services…"))
        self.restart_btn = Gtk.Button(label="Restart", icon_name="view-refresh-symbolic", valign=Gtk.Align.CENTER)
        self.restart_btn.connect("clicked", lambda *_: self.win.run_verb(["restart", "all"], "Restarting all services…"))
        for b in (self.start_btn, self.stop_btn, self.restart_btn):
            head.append(b)
        body.append(head)

        # ── all 8 cards in ONE responsive grid: Web/PHP/DB/Cache + CPU/Mem/Storage/Net,
        #    laid out 4+4 on wide, 2+2+2+2 on medium, stacked on narrow ──
        cards = CardGrid()
        self.c_web = self._status_card("Web Server")
        self.c_php = self._status_card("PHP")
        self.c_db = self._status_card("Database")
        self.c_cache = self._status_card("Cache")
        self.cpu_val, cpu_card = self._cpu_card()
        self.mem = self._bar_card("Memory")
        self.disk = self._bar_card("Storage")
        self.net_down, self.net_up, net_card = self._net_card()
        for c in (self.c_web["card"], self.c_php["card"], self.c_db["card"], self.c_cache["card"],
                  cpu_card, self.mem["card"], self.disk["card"], net_card):
            cards.add_card(c)
        body.append(cards)

        # ── websites panel ──
        self.web_header = Gtk.Label(label="Websites", xalign=0, css_classes=["title-4"])
        body.append(self.web_header)
        self.site_list = PagedList(lambda s: build_site_row(self.win, s), site_match,
                                   page_size=self.win.cfg_int("dashboard_page_size", 5),
                                   empty_text="No sites yet — add one from the Sites tab.",
                                   on_page_size_changed=lambda n: self.win.set_cfg("dashboard_page_size", n),
                                   scroll=False)
        body.append(self.site_list)

        # ── web tools ──
        body.append(Gtk.Label(label="Web tools", xalign=0, css_classes=["title-4"]))
        tools = CardGrid()
        self.t_pma = self._tool_card("phpMyAdmin", "phpmyadmin", ["pma", "install"])
        self.t_adm = self._tool_card("Adminer", "adminer", ["adminer", "install"])
        self.t_mail = self._tool_card("Mailpit", "mailpit", ["mailpit", "setup"])
        for t in (self.t_pma, self.t_adm, self.t_mail):
            tools.add_card(t["card"])
        body.append(tools)

        # ── activity log ──
        self.log_expander = Gtk.Expander(label="Activity log")
        self.log_view = Gtk.TextView(editable=False, monospace=True, css_classes=["card"])
        log_sc = Gtk.ScrolledWindow(min_content_height=150)
        log_sc.set_child(self.log_view)
        self.log_expander.set_child(log_sc)
        body.append(self.log_expander)

    # ── card builders ──
    def _status_card(self, title):
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3, css_classes=["card", "bh-metric"])
        top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        top.append(Gtk.Label(label=title, xalign=0, hexpand=True, css_classes=["bh-metric-cap", "dim-label"]))
        dot = status_dot(False)
        top.append(dot)
        card.append(top)
        # Wrap (don't stretch) a long value like the PHP-versions list, so it can't inflate the card
        # width and break the 4-per-row grid; it flows to a 2nd line inside the fixed-width card.
        val = Gtk.Label(label="—", xalign=0, css_classes=["bh-metric-val"], wrap=True,
                        wrap_mode=Pango.WrapMode.WORD_CHAR, max_width_chars=18)
        sub = Gtk.Label(label="", xalign=0, css_classes=["dim-label"])
        card.append(val)
        card.append(sub)
        return {"card": card, "val": val, "sub": sub, "dot": dot}

    def _cpu_card(self):
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3, css_classes=["card", "bh-metric"])
        card.append(Gtk.Label(label="CPU", xalign=0, css_classes=["bh-metric-cap", "dim-label"]))
        val = Gtk.Label(label="0%", xalign=0, css_classes=["bh-metric-val"])
        card.append(val)
        self.spark = Gtk.DrawingArea(content_height=34, hexpand=True)
        if _HAVE_CAIRO:
            self.spark.set_draw_func(self._draw_spark)
        card.append(self.spark)
        return val, card

    def _bar_card(self, title):
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3, css_classes=["card", "bh-metric"])
        card.append(Gtk.Label(label=title, xalign=0, css_classes=["bh-metric-cap", "dim-label"]))
        val = Gtk.Label(label="—", xalign=0, css_classes=["bh-metric-val"])
        card.append(val)
        bar = Gtk.ProgressBar()
        card.append(bar)
        return {"card": card, "val": val, "bar": bar}

    def _net_card(self):
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3, css_classes=["card", "bh-metric"])
        card.append(Gtk.Label(label="Network", xalign=0, css_classes=["bh-metric-cap", "dim-label"]))
        down = Gtk.Label(label="Down  —", xalign=0)
        up = Gtk.Label(label="Up  —", xalign=0)
        card.append(down)
        card.append(up)
        return down, up, card

    def _tool_card(self, title, site_name, on_verb):
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, css_classes=["card", "bh-metric"])
        card.append(Gtk.Label(label=title, xalign=0, css_classes=["bh-metric-cap"]))
        status = Gtk.Label(label="Off", xalign=0, css_classes=["dim-label"])
        card.append(status)
        bottom = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        sw = Gtk.Switch(valign=Gtk.Align.CENTER)
        sw.connect("notify::active", lambda s, _p, n=site_name, v=on_verb: self._tool_toggled(n, v, s.get_active()))
        bottom.append(sw)
        bottom.append(Gtk.Label(label="", hexpand=True))
        openb = Gtk.Button(label="Open", valign=Gtk.Align.CENTER)
        openb.connect("clicked", lambda *_, t=site_name: self._tool_open(t))
        bottom.append(openb)
        card.append(bottom)
        return {"card": card, "switch": sw, "status": status, "open": openb, "url": ""}

    # ── drawing ──
    def _draw_spark(self, area, cr, w, h):
        pts = list(self.cpu_hist)
        if len(pts) < 2:
            return
        cr.set_source_rgb(0.051, 0.431, 0.992)  # #0d6efd
        cr.set_line_width(2)
        n = len(pts)
        for i, v in enumerate(pts):
            x = i * w / (n - 1)
            y = h - (v / 100.0) * (h - 2) - 1
            cr.line_to(x, y) if i else cr.move_to(x, y)
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
        secure = bool(site and site.get("secure"))
        t["status"].set_label(("Active · https" if secure else "Active") if active else "Off")
        t["url"] = ((("https://" if secure else "http://") + site["domain"]) if active and site else "")

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
                   f"{len(php_vers)} installed", any(s["role"] == "php" and s.get("running") for s in services))
        maria, my, pg = run("mariadb"), run("mysql"), run("postgresql@16") or run("postgresql")
        dbrun = maria or my or pg
        self._fill(self.c_db, "MariaDB" if maria else "MySQL" if my else "PostgreSQL" if pg else "MySQL / MariaDB",
                   "running" if dbrun else "stopped", dbrun)
        redis, memc = run("redis"), run("memcached")
        self._fill(self.c_cache, "Redis · Memcached",
                   f"redis {'on' if redis else 'off'}, memcached {'on' if memc else 'off'}", redis or memc)

        self.subtitle.set_label(f"{sum(1 for s in services if s.get('running'))} services running · {len(sites)} sites")

        cpu = self.cpu.percent()
        self.cpu_val.set_label(f"{cpu:.0f}%")
        self.cpu_hist.append(cpu)
        if _HAVE_CAIRO:
            self.spark.queue_draw()
        mu, mt, mp = memory()
        self.mem["val"].set_label(f"{mu:.1f} / {mt:.1f} GB")
        self.mem["bar"].set_fraction(min(1.0, mp / 100))
        du, dt, dp = disk()
        self.disk["val"].set_label(f"{du:.0f} / {dt:.0f} GB")
        self.disk["bar"].set_fraction(min(1.0, dp / 100))
        down, up = self.net.rate_kbps()
        self.net_down.set_label(f"Down  {rate_str(down)}")
        self.net_up.set_label(f"Up  {rate_str(up)}")

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

        log = "\n".join(getattr(self.win, "applog", [])[-200:])
        if self.log_view.get_buffer().get_char_count() != len(log):
            self.log_view.get_buffer().set_text(log)

    def _fill(self, card, val, sub, on):
        card["val"].set_label(val)
        card["sub"].set_label(sub)
        _set_dot(card["dot"], on)
