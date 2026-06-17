"""Tiny strategy registry: register / lookup / list.

Strategies register by their ``name``. Adding a new strategy to the library is one
``@register`` decorator away — the evaluation harness then scores it automatically.
"""

import logging

log = logging.getLogger(__name__)

_REGISTRY: dict[str, type] = {}


def register(strategy_cls: type) -> type:
    """Class decorator: register a Strategy subclass under its ``name``."""
    name = getattr(strategy_cls, "name", None)
    if not name:
        raise ValueError(f"{strategy_cls.__name__} must define a non-empty 'name'.")
    if name in _REGISTRY and _REGISTRY[name] is not strategy_cls:
        log.warning("Overriding already-registered strategy '%s'.", name)
    _REGISTRY[name] = strategy_cls
    return strategy_cls


def get(name: str) -> type:
    """Return the registered strategy class for ``name``."""
    return _REGISTRY[name]


def names() -> list[str]:
    """List registered strategy names (registration order)."""
    return list(_REGISTRY)


def all_strategies() -> dict[str, type]:
    """Return a copy of the registry mapping name -> class."""
    return dict(_REGISTRY)
