"""Logs pane: professional flat dashboard-style log viewer with overview cards,
service log file switcher, search filter, and syntax-highlighted console output.
"""
from __future__ import annotations

import os
import re

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk, Pango  # noqa: E402

from ..widgets import pill, status_dot, status_pill
from ._shared import CardGrid, _open, clean_version

LINE_LIMITS = [
    ("100", 100),
    ("250", 250),
    ("500", 500),
    ("1000", 1000),
    ("All lines", 100000),
]


class LogsPage(Gtk.Box):
    def __init__(self, win) -> None:
        super().__init__(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=14,
            margin_top=18,
            margin_bottom=18,
            margin_start=18,
            margin_end=18,
        )
        self.win = win
        self._files: list[str] = []
        self._raw_lines: list[str] = []
        self._search_query = ""
        self._line_limit = 500

        # ── 1. Header: title + subtitle + quick actions ──
        head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        tb = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
        tb.append(Gtk.Label(label="Logs & Diagnostics", xalign=0, css_classes=["title-1"]))
        self.subtitle = Gtk.Label(
            label="View live server, runtime, database, process, and error logs in real time",
            xalign=0,
            css_classes=["dim-label"],
        )
        tb.append(self.subtitle)
        head.append(tb)

        btn_group = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            css_classes=["bh-button-group", "linked"],
            valign=Gtk.Align.CENTER,
        )

        copy_b = Gtk.Button(
            icon_name="edit-copy-symbolic",
            tooltip_text="Copy log content to clipboard",
        )
        copy_b.connect("clicked", lambda *_: self._copy_log())
        btn_group.append(copy_b)

        clear_b = Gtk.Button(
            icon_name="edit-clear-symbolic",
            tooltip_text="Clear active log file",
        )
        clear_b.connect("clicked", lambda *_: self._clear_active_log())
        btn_group.append(clear_b)

        folder_b = Gtk.Button(
            icon_name="folder-symbolic",
            tooltip_text="Open logs directory (~/.omniserv/logs)",
        )
        folder_b.connect("clicked", lambda *_: self._open_logs_folder())
        btn_group.append(folder_b)

        head.append(btn_group)
        self.append(head)

        # ── 2. Top Summary Metric Cards (CardGrid) ──
        cards = CardGrid()
        self.c_active = self._metric_card("Active Log")
        self.c_total = self._metric_card("Total Logs")
        self.c_errs = self._metric_card("Diagnostics")
        self.c_loc = self._metric_card("Storage")
        for c in (
            self.c_active["card"],
            self.c_total["card"],
            self.c_errs["card"],
            self.c_loc["card"],
        ):
            cards.add_card(c)
        self.append(cards)

        # ── 3. Control Toolbar: File selector + Search filter + Line count + Reload ──
        ctrl_bar = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=10,
            valign=Gtk.Align.CENTER,
        )

        # Log file dropdown
        ctrl_bar.append(Gtk.Label(label="Log file:", css_classes=["dim-label"]))
        self.dd = Gtk.DropDown.new_from_strings(["(refresh)"])
        self.dd.set_size_request(240, -1)
        self.dd.connect("notify::selected", lambda *_: self._load())
        ctrl_bar.append(self.dd)

        # Search filter entry
        self.search_entry = Gtk.SearchEntry(
            placeholder_text="Filter log output (e.g. error, 500, warning, path)…",
        )
        self.search_entry.set_hexpand(True)
        self.search_entry.connect("search-changed", self._on_search_changed)
        ctrl_bar.append(self.search_entry)

        # Lines picker
        ctrl_bar.append(Gtk.Label(label="Show:", css_classes=["dim-label"]))
        self.lines_dd = Gtk.DropDown.new_from_strings([l[0] for l in LINE_LIMITS])
        self.lines_dd.set_selected(2)  # Default: 500
        self.lines_dd.connect("notify::selected", self._on_line_limit_changed)
        ctrl_bar.append(self.lines_dd)

        # Reload button
        reload_b = Gtk.Button(
            icon_name="view-refresh-symbolic",
            tooltip_text="Reload log file from disk",
        )
        reload_b.connect("clicked", lambda *_: self._load())
        ctrl_bar.append(reload_b)

        self.append(ctrl_bar)

        # ── 4. Console Log Viewer (Dock Container) ──
        dock = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            css_classes=["bh-console-dock"],
            vexpand=True,
            hexpand=True,
        )

        dock_hdr = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=8,
            css_classes=["bh-console-header"],
        )
        dock_hdr.append(Gtk.Image.new_from_icon_name("text-x-generic-symbolic"))
        self.console_title = Gtk.Label(label="Console Output", css_classes=["heading"])
        dock_hdr.append(self.console_title)
        dock_hdr.append(status_dot(True))

        dock_hdr.append(Gtk.Box(hexpand=True))
        self.log_stat_pill = pill("0 lines", "bh-pill-off")
        dock_hdr.append(self.log_stat_pill)
        dock.append(dock_hdr)

        self.text_view = Gtk.TextView(
            editable=False,
            monospace=True,
            css_classes=["bh-console-body"],
            wrap_mode=Gtk.WrapMode.NONE,
        )
        buf = self.text_view.get_buffer()
        self.tag_time = buf.create_tag("time", foreground="#6b7280", scale=0.9)
        self.tag_err = buf.create_tag("err", foreground="#f87171", weight=Pango.Weight.BOLD)
        self.tag_warn = buf.create_tag("warn", foreground="#f59e0b", weight=Pango.Weight.BOLD)
        self.tag_ok = buf.create_tag("ok", foreground="#2ec27e", weight=Pango.Weight.BOLD)
        self.tag_normal = buf.create_tag("normal", foreground="#e4e7eb")

        scroller = Gtk.ScrolledWindow(vexpand=True, hexpand=True)
        scroller.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroller.set_child(self.text_view)
        dock.append(scroller)

        self.append(dock)

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
        badge = pill("● Active", "bh-pill-on")
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

    # ── Handlers & Actions ──
    def _on_search_changed(self, entry: Gtk.SearchEntry) -> None:
        self._search_query = entry.get_text().strip().lower()
        self._render_log_buffer()

    def _on_line_limit_changed(self, dropdown, _param) -> None:
        idx = dropdown.get_selected()
        if 0 <= idx < len(LINE_LIMITS):
            self._line_limit = LINE_LIMITS[idx][1]
            self._load()

    def _open_logs_folder(self) -> None:
        logdir = os.path.expanduser("~/.omniserv/logs")
        if os.path.isdir(logdir):
            _open(logdir)
        else:
            _open(os.path.expanduser("~/.omniserv"))

    def _copy_log(self) -> None:
        buf = self.text_view.get_buffer()
        start, end = buf.get_bounds()
        text = buf.get_text(start, end, False)
        if text:
            self.win._copy(text)
            self.win.toast("Log contents copied to clipboard")

    def _clear_active_log(self) -> None:
        if not self._files:
            return
        idx = self.dd.get_selected()
        if idx < 0 or idx >= len(self._files):
            return
        fname = self._files[idx]
        path = os.path.expanduser(f"~/.omniserv/logs/{fname}")
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write("")
            self.win.toast(f"Cleared {fname}")
            self._load()
        except Exception as e:
            self.win.toast(f"Error clearing log: {e}")

    # ── Refresh & Loading ──
    def refresh(self, data: dict) -> None:
        logdir = os.path.expanduser("~/.omniserv/logs")
        files = sorted(os.listdir(logdir)) if os.path.isdir(logdir) else []
        old_selected = self._files[self.dd.get_selected()] if (self._files and self.dd.get_selected() < len(self._files)) else None

        self._files = files
        model = Gtk.StringList.new(files or ["(no logs found)"])
        self.dd.set_model(model)

        if old_selected and old_selected in files:
            self.dd.set_selected(files.index(old_selected))
        elif files:
            self.dd.set_selected(0)

        # Update static storage card
        self.c_loc["val"].set_label("~/.omniserv/logs")
        self.c_loc["sub"].set_label("Log files directory")
        self._set_card_badge(self.c_loc["badge"], "● Ready", "bh-pill-blue")

        self.c_total["val"].set_label(f"{len(files)} Logs" if len(files) != 1 else "1 Log")
        self.c_total["sub"].set_label("Nginx, Apache, PHP, Databases, Apps")
        self._set_card_badge(self.c_total["badge"], "● Active" if files else "● Empty", "bh-pill-on" if files else "bh-pill-off")

        if self._files:
            self._load()

    def _load(self) -> None:
        if not self._files:
            self.text_view.get_buffer().set_text("# No log files found in ~/.omniserv/logs")
            return
        idx = self.dd.get_selected()
        if idx < 0 or idx >= len(self._files):
            return

        fname = self._files[idx]
        path = os.path.expanduser(f"~/.omniserv/logs/{fname}")

        file_size = 0
        try:
            file_size = os.path.getsize(path)
            with open(path, "r", errors="replace") as f:
                lines = f.readlines()
                self._raw_lines = lines[-self._line_limit:]
        except Exception as e:
            self._raw_lines = [f"# Error reading {path}: {e}\n"]

        # Update active log metric card
        size_str = f"{file_size / 1024:.1f} KB" if file_size < 1024 * 1024 else f"{file_size / (1024 * 1024):.2f} MB"
        self.c_active["val"].set_label(fname)
        self.c_active["sub"].set_label(f"{size_str} · Showing last {len(self._raw_lines)} lines")
        self._set_card_badge(self.c_active["badge"], "● Loaded", "bh-pill-on")

        self.console_title.set_label(f"Console Output: {fname}")
        self.subtitle.set_label(
            f"Viewing {fname} ({size_str}) · {len(self._files)} total log files available in ~/.omniserv/logs"
        )

        self._render_log_buffer()

    def _render_log_buffer(self) -> None:
        buf = self.text_view.get_buffer()
        buf.set_text("")

        q = self._search_query
        filtered_lines = [
            ln for ln in self._raw_lines
            if not q or q in ln.lower()
        ]

        err_cnt = 0
        warn_cnt = 0

        for line in filtered_lines:
            low = line.lower()
            if "error" in low or "crit" in low or "emerg" in low or "failed" in low or "fatal" in low:
                err_cnt += 1
                tag = self.tag_err
            elif "warn" in low:
                warn_cnt += 1
                tag = self.tag_warn
            elif "200" in low or "ok" in low or "success" in low or "ready" in low or "started" in low:
                tag = self.tag_ok
            else:
                tag = self.tag_normal

            # Highlight leading timestamp if present
            m_time = re.match(r"^(\[?[0-9]{4}[-/][0-9]{2}[-/][0-9]{2}[ T][0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]+)?\]?)(.*)$", line)
            end_iter = buf.get_end_iter()
            if m_time:
                buf.insert_with_tags(end_iter, m_time.group(1), self.tag_time)
                end_iter = buf.get_end_iter()
                buf.insert_with_tags(end_iter, m_time.group(2) + "\n", tag)
            else:
                buf.insert_with_tags(end_iter, line if line.endswith("\n") else line + "\n", tag)

        # Update error / diagnostics card
        if err_cnt > 0:
            self.c_errs["val"].set_label(f"{err_cnt} Errors")
            self.c_errs["sub"].set_label(f"{warn_cnt} warnings in active view")
            self._set_card_badge(self.c_errs["badge"], "● Alert", "bh-pill-warn")
        elif warn_cnt > 0:
            self.c_errs["val"].set_label(f"{warn_cnt} Warnings")
            self.c_errs["sub"].set_label("No critical errors found")
            self._set_card_badge(self.c_errs["badge"], "● Notice", "bh-pill-warn")
        else:
            self.c_errs["val"].set_label("All Clean")
            self.c_errs["sub"].set_label("No errors detected in view")
            self._set_card_badge(self.c_errs["badge"], "● Clear", "bh-pill-on")

        self.log_stat_pill.set_label(f"{len(filtered_lines)} of {len(self._raw_lines)} lines")

