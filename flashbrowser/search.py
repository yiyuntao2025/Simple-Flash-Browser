from __future__ import annotations

import re
import urllib.parse

SEARCH_ENGINES = {
    "bing": {
        "label": "Bing",
        "template": "https://www.bing.com/search?q={query}",
    },
    "baidu": {
        "label": "百度",
        "template": "https://www.baidu.com/s?wd={query}",
    },
    "google": {
        "label": "Google",
        "template": "https://www.google.com/search?q={query}",
    },
}
SEARCH_ORDER = ("bing", "baidu", "google")
DEFAULT_SEARCH_ENGINE = "bing"
THEME_MODES = ("system", "light", "dark")


def normalize_engine(name: str | None) -> str:
    return name if name in SEARCH_ENGINES else DEFAULT_SEARCH_ENGINE


def engine_label(name: str | None) -> str:
    return SEARCH_ENGINES[normalize_engine(name)]["label"]


def build_search_url(query: str, engine: str = DEFAULT_SEARCH_ENGINE) -> str:
    template = SEARCH_ENGINES[normalize_engine(engine)]["template"]
    return template.format(query=urllib.parse.quote_plus(query.strip()))


def is_windows_path(text: str) -> bool:
    return bool(re.match(r"^[a-zA-Z]:[\\/]", text) or text.startswith("\\\\"))


def _is_ipv4(host: str) -> bool:
    candidate = host.split(":", 1)[0]
    parts = candidate.split(".")
    if len(parts) != 4:
        return False
    return all(part.isdigit() and 0 <= int(part) <= 255 for part in parts)


def looks_like_url(text: str) -> bool:
    value = text.strip()
    if not value:
        return False
    if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", value):
        return True
    if re.match(
        r"^(?:https?|ftp|file|about|data|mailto|view-source):",
        value,
        re.IGNORECASE,
    ):
        return True
    if is_windows_path(value):
        return True

    host = re.split(r"[/?#\\]", value, maxsplit=1)[0]
    if "@" in host:
        host = host.rsplit("@", 1)[-1]
    if not host:
        return False
    if host.startswith("["):
        return True
    if re.match(r"^localhost(?::\d+)?$", host, re.IGNORECASE):
        return True
    if _is_ipv4(host):
        return True
    if re.match(r"^[^\s:/]+:\d+$", host):
        return True
    if re.match(r"^\d+(?:\.\d+)*$", host):
        return False
    return bool(re.match(r"^[^\s/:]+(?:\.[^\s/:]+)+\.?$", host))
