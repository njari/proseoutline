"""
experiment/registry.py — plug function registry.

Plug functions are registered at import time via the @plug decorator.
Built-in plugs are registered when `experiment.plugs` is imported.
"""

import re
from pathlib import Path
from typing import Callable

PlugFunction = Callable[[Path, Path, dict], None]

_REGISTRY: dict[str, PlugFunction] = {}

_KEY_RE = re.compile(r"^[a-z0-9_]+$")


def plug(key: str) -> Callable[[PlugFunction], PlugFunction]:
    """
    Decorator — registers a plug function under `key`.

    The key must match [a-z0-9_]+ and must be unique across all registered plugs.

    Usage::

        @plug("my_transform")
        def run(input_path: Path, output_path: Path, config: dict) -> None:
            ...
    """
    if not _KEY_RE.match(key):
        raise ValueError(
            f"Plug key {key!r} is invalid. Keys must match [a-z0-9_]+."
        )

    def decorator(fn: PlugFunction) -> PlugFunction:
        if key in _REGISTRY:
            raise ValueError(f"Plug key {key!r} is already registered.")
        _REGISTRY[key] = fn
        return fn

    return decorator


def get_plug(key: str) -> PlugFunction:
    if key not in _REGISTRY:
        raise KeyError(
            f"No plug registered for key {key!r}. "
            f"Registered plugs: {list(_REGISTRY.keys())}"
        )
    return _REGISTRY[key]


def registered_keys() -> list[str]:
    return list(_REGISTRY.keys())
