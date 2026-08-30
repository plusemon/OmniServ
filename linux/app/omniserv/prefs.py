"""GUI preferences store — manages ~/.omniserv/config/gui.json (separate from engine config)."""
from __future__ import annotations

import json
import os

GUI_CFG = os.path.expanduser("~/.omniserv/config/gui.json")


def get_gui_cfg() -> dict:
    try:
        if os.path.exists(GUI_CFG):
            with open(GUI_CFG) as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def cfg_int(key: str, default: int) -> int:
    try:
        return int(get_gui_cfg().get(key, default))
    except (ValueError, TypeError):
        return default


def cfg_bool(key: str, default: bool) -> bool:
    val = get_gui_cfg().get(key, default)
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.lower() in ("true", "1", "yes", "on")
    return bool(val)


def set_cfg(key: str, value: object) -> None:
    d = get_gui_cfg()
    d[key] = value
    os.makedirs(os.path.dirname(GUI_CFG), exist_ok=True)
    with open(GUI_CFG, "w") as f:
        json.dump(d, f, indent=2)
