from __future__ import annotations

import os


def get_secret(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if value:
        return value
    if os.name != "nt":
        return ""
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
            registry_value, _kind = winreg.QueryValueEx(key, name)
    except OSError:
        return ""
    return str(registry_value).strip()
