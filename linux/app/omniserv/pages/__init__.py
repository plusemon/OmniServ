"""The 8 panes (parity with macOS v1.7.4): Dashboard / Services / Sites / Databases /
Node / Python / Logs / Settings. Each Page is a Gtk.Box with a refresh(api) method the
window calls after every `omniserv api` snapshot.
"""
from __future__ import annotations

from ._shared import (
    PHP_KEYS,
    ROLE_LABEL,
    SERVICE_GROUPS,
    CardGrid,
    SiteConfigDialog,
    _is_ols,
    _open,
    _open_editor,
    _open_text_editor,
    _open_terminal,
    build_site_row,
    clean_version,
    is_tool,
    site_change_php,
    site_change_root,
    site_match,
)
from .dashboard import DashboardPage
from .databases import DatabasesPage
from .logs import LogsPage
from .node import NodePage, _AppsPage
from .python import PythonPage
from .services import ServicesPage
from .settings import SettingsPage
from .sites import SitesPage

__all__ = [
    "PHP_KEYS",
    "ROLE_LABEL",
    "SERVICE_GROUPS",
    "CardGrid",
    "SiteConfigDialog",
    "clean_version",
    "is_tool",
    "site_match",
    "build_site_row",
    "site_change_php",
    "site_change_root",
    "_open",
    "_open_editor",
    "_open_text_editor",
    "_open_terminal",
    "_is_ols",
    "_AppsPage",
    "DashboardPage",
    "ServicesPage",
    "SitesPage",
    "NodePage",
    "PythonPage",
    "DatabasesPage",
    "LogsPage",
    "SettingsPage",
]
