"""Python apps pane: Python environment management and managed Python application list."""
from __future__ import annotations

from ._shared import clean_version
from .node import _AppsPage


class PythonPage(_AppsPage):
    KIND, TITLE = "py", "Python apps"

    def refresh(self, data):
        py = next((s for s in data.get("services", []) if s["key"] == "python"), {})
        inst = py.get("installed")
        self.rt_row.set_title("Python" + (f" {clean_version(py.get('version',''))}" if inst else " — not installed"))
        self.rt_row.set_subtitle("Ready for venv-backed apps" if inst else "Install Python to run Python apps")
        self._set_runtime_btn(None if inst else "Install Python",
                              lambda: self.win.run_progress(
                                  ["install", "python"], "Installing Python",
                                  "Setting up Python with venv support…", "Python installed."))
        super().refresh(data)
