"""Web-specific config loading helpers."""

from __future__ import annotations

from typing import Any

import yaml


def load_config_preserving_root(path: str) -> Any:
    """Load YAML while preserving non-mapping roots for web validation."""
    with open(path, "r") as stream:
        loaded = yaml.load(stream, Loader=yaml.SafeLoader)
    return {} if loaded is None else loaded
