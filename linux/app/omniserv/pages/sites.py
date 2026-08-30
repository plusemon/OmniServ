"""Sites pane: websites list with search, pagination, and Add Site action."""
from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

from ..widgets import PagedList
from ._shared import build_site_row, is_tool, site_match


class SitesPage(Gtk.Box):
    def __init__(self, win) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=14,
                         margin_top=18, margin_bottom=18, margin_start=18, margin_end=18)
        self.win = win
        self.header_label = Gtk.Label(label="Websites", xalign=0, css_classes=["title-2"])
        self.append(self.header_label)

        add = Gtk.Button(label="Add site", icon_name="list-add-symbolic", css_classes=["suggested-action"],
                         valign=Gtk.Align.CENTER)
        add.connect("clicked", lambda *_: self._add_dialog())

        self.list = PagedList(lambda s: build_site_row(self.win, s), site_match,
                              page_size=self.win.cfg_int("sites_page_size", 15),
                              empty_text="No sites yet — click “Add site”.",
                              on_page_size_changed=lambda n: self.win.set_cfg("sites_page_size", n),
                              extra_action=add)
        self.append(self.list)

    def refresh(self, data: dict) -> None:
        # phpMyAdmin / Adminer / Mailpit are built-in tools, not user sites — they're managed
        # from Services + the dashboard web-tools, so keep them out of the Sites list.
        sites = [s for s in data.get("sites", []) if not is_tool(s.get("name", ""))]
        self.header_label.set_label(f"Websites ({len(sites)})")
        self.list.set_items(sites)

    def _add_dialog(self):
        self.win.add_site_dialog()
