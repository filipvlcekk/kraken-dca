"""Web-specific config loading helpers."""

from __future__ import annotations

from typing import Any

import yaml


def load_config_preserving_root(path: str) -> Any:
    """Load YAML while preserving non-mapping roots for web validation."""
    try:
        with open(path, "r", encoding="utf-8") as stream:
            loaded = yaml.load(stream, Loader=yaml.SafeLoader)
    except UnicodeDecodeError as exc:
        raise yaml.YAMLError("Config YAML is malformed.") from exc
    return {} if loaded is None else loaded
