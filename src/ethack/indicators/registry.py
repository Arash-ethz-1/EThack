# Indicator registry. Import a module in impl/ and it registers itself.
# OWNER: Arash.

from __future__ import annotations

import importlib
import pkgutil
from typing import Iterator

from .base import Durability, Indicator, IndicatorSpec

_REGISTRY: dict[str, Indicator] = {}


def register(cls: type[Indicator]) -> type[Indicator]:
    # Decorator. Put @register above every Indicator subclass in impl/.
    inst = cls()
    if inst.spec.id in _REGISTRY:
        raise ValueError(f"duplicate indicator id {inst.spec.id!r}")
    _REGISTRY[inst.spec.id] = inst
    return cls


def _autoload() -> None:
    from . import impl

    for mod in pkgutil.iter_modules(impl.__path__):
        importlib.import_module(f"{impl.__name__}.{mod.name}")


def get(indicator_id: str) -> Indicator:
    if not _REGISTRY:
        _autoload()
    return _REGISTRY[indicator_id]


def all_indicators() -> list[Indicator]:
    if not _REGISTRY:
        _autoload()
    return list(_REGISTRY.values())


def all_specs() -> list[IndicatorSpec]:
    return [i.spec for i in all_indicators()]


def surviving(dead_sources: frozenset[str] = frozenset()) -> list[Indicator]:
    # The indicators that remain computable after the given sources disappear.
    # The dashboard's blackout page calls exactly this.
    return [i for i in all_indicators() if i.available(dead_sources)]


def by_dimension() -> dict[str, list[Indicator]]:
    out: dict[str, list[Indicator]] = {}
    for ind in all_indicators():
        out.setdefault(ind.spec.dimension.value, []).append(ind)
    return out


def durability_profile() -> dict[str, int]:
    # How exposed is our framework? Count indicators per durability class.
    # If most of your score sits in AT_RISK, that is the finding, not a bug.
    prof: dict[str, int] = {d.value: 0 for d in Durability}
    for spec in all_specs():
        prof[spec.durability.value] += 1
    return prof
