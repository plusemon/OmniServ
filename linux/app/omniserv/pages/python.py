"""Python apps pane: Python environment management and managed Python application list."""
from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk  # noqa: E402

from ..widgets import pill, status_dot
from ._shared import clean_version
from .node import _AppsPage


class PythonPage(_AppsPage):
    KIND, TITLE = "py", "Python Applications"
    SUBTITLE_DESC = "Python applications, virtualenvs, and WSGI/ASGI processes"

    def _update_metrics(self, data: dict) -> None:
        py = next((s for s in data.get("services", []) if s.get("key") == "python"), {})
        inst = py.get("installed")
        v = clean_version(py.get("version", ""))

        total_apps = len(self._last_apps)
        running_apps = sum(1 for a in self._last_apps if a.get("running"))

        # 1. Runtime Version
        if inst:
            self.c_rt["val"].set_label(f"Python {v}" if v else "Python 3")
            self.c_rt["sub"].set_label("System & venv runtime")
            self._set_card_badge(self.c_rt["badge"], "● Ready", "bh-pill-on")
        else:
            self.c_rt["val"].set_label("Not Installed")
            self.c_rt["sub"].set_label("Python 3 environment")
            self._set_card_badge(self.c_rt["badge"], "● Inactive", "bh-pill-off")

        # 2. Total Applications
        self.c_apps["val"].set_label(f"{total_apps} Apps" if total_apps != 1 else "1 App")
        self.c_apps["sub"].set_label(f"{running_apps} active Python processes")
        self._set_card_badge(
            self.c_apps["badge"],
            "● Live" if running_apps > 0 else ("● Idle" if total_apps > 0 else "● Empty"),
            "bh-pill-on" if running_apps > 0 else "bh-pill-off",
        )

        # 3. Virtualenv / pip
        self.c_pm["val"].set_label("venv / pip")
        self.c_pm["sub"].set_label("Isolated virtual environments")
        self._set_card_badge(self.c_pm["badge"], "● Ready" if inst else "● Offline", "bh-pill-blue" if inst else "bh-pill-off")

        # 4. Gateway
        self.c_proxy["val"].set_label("Nginx Gateway")
        self.c_proxy["sub"].set_label("Reverse proxy to ASGI / WSGI ports")
        self._set_card_badge(self.c_proxy["badge"], "● Live", "bh-pill-on")

        self.subtitle.set_label(
            f"{total_apps} applications · {running_apps} active processes · Python {v or '3'} virtualenv"
        )

    def _render_runtime_section(self, data: dict) -> None:
        child = self.rt_container.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self.rt_container.remove(child)
            child = nxt

        py = next((s for s in data.get("services", []) if s.get("key") == "python"), {})
        inst = py.get("installed")
        v = clean_version(py.get("version", ""))

        hdr_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        hdr_box.append(Gtk.Label(label="Runtime Environment", xalign=0, css_classes=["title-4"]))
        if inst:
            hdr_box.append(pill(f"Python {v or '3'}", "bh-pill-on"))
        self.rt_container.append(hdr_box)

        listbox = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE, css_classes=["boxed-list"])
        row = Adw.ActionRow(
            title=f"Python {v}" if inst else "Python 3 — Not Installed",
            subtitle="Ready for virtualenv-backed applications (FastAPI, Flask, Django)" if inst else "Install Python with venv support to run Python applications",
        )
        row.add_prefix(status_dot(inst))

        suffix = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6, valign=Gtk.Align.CENTER)

        if not inst:
            inst_btn = Gtk.Button(
                label="Install Python",
                icon_name="list-add-symbolic",
                css_classes=["suggested-action"],
                valign=Gtk.Align.CENTER,
            )
            inst_btn.connect(
                "clicked",
                lambda *_: self.win.run_progress(
                    ["install", "python"],
                    "Installing Python",
                    "Setting up Python with venv support…",
                    "Python installed.",
                ),
            )
            suffix.append(inst_btn)
            self._set_runtime_btn(
                "Install Python",
                lambda: self.win.run_progress(
                    ["install", "python"],
                    "Installing Python",
                    "Setting up Python with venv support…",
                    "Python installed.",
                ),
            )
        else:
            suffix.append(pill("● Installed", "bh-pill-on"))
            self._set_runtime_btn(None)

        row.add_suffix(suffix)
        listbox.append(row)
        self.rt_container.append(listbox)

