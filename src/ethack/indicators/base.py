# The indicator plugin interface.
# OWNER: Arash. Lauren owns the implementations in impl/.
#
# An indicator is a declaration plus a pure function. The declaration is what makes
# the dashboard self-generating and the blackout simulator possible: because every
# indicator names its sources and rates their durability, we can ask "what survives
# if EPA GHGRP goes away?" and get an honest answer instead of a guess.

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import ClassVar

import pandas as pd


class Durability(str, Enum):
    # How politically erasable is the underlying data?
    PERMANENT = "permanent"    # satellites, market prices - no administration can rescind these
    STATUTORY = "statutory"    # core securities law: 10-K financials, EX-21 subsidiary lists
    AT_RISK = "at_risk"        # mandatory environmental disclosure under active rollback
    VOLUNTARY = "voluntary"    # the company decides whether it exists at all
    DERIVED = "derived"        # computed from other indicators


class Dimension(str, Enum):
    ENVIRONMENTAL = "environmental"
    FINANCIAL = "financial"
    OPERATIONAL = "operational"
    GOVERNANCE = "governance"
    CREDIBILITY = "credibility"


@dataclass(frozen=True)
class IndicatorSpec:
    id: str
    name: str
    dimension: Dimension
    durability: Durability
    sources: tuple[str, ...]        # source ids, must match ethack.sources registry
    direction: int                  # +1 higher is better, -1 lower is better
    unit: str
    rationale: str                  # WHY. This sentence goes on the methodology slide.
    default_weight: float = 1.0
    min_coverage: float = 0.30      # below this the indicator abstains rather than guesses

    def __post_init__(self) -> None:
        assert self.direction in (1, -1), f"{self.id}: direction must be +1 or -1"
        assert self.rationale.strip(), f"{self.id}: rationale is mandatory"
        assert self.sources, f"{self.id}: must declare at least one source"


class Indicator:
    # Subclass this, set `spec`, implement `compute`. Register with @register.
    spec: ClassVar[IndicatorSpec]

    def compute(self, panel: pd.DataFrame) -> pd.Series:
        # Return a float Series indexed by ticker. Raw units, not normalised -
        # score.py owns normalisation so that every indicator is comparable.
        #
        # Return NaN for companies where the input genuinely does not exist.
        # NEVER return 0 for missing data: a zero is a claim, NaN is the truth.
        raise NotImplementedError

    def available(self, dead_sources: frozenset[str] = frozenset()) -> bool:
        # Can this indicator still be computed if `dead_sources` have gone away?
        # This is the whole blackout simulator in one method.
        return not (set(self.spec.sources) & set(dead_sources))
