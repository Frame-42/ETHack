"""Economic viability pillar: can a company keep paying its workforce
and obligations out of its own operations — also through a bad year?

Moved here from branch ``feat/economy`` into the unified clean framework.
See ``report/economic_viability.tex`` for the full derivation
(capacity not profit, observed not forecast, weakest link).

Thin re-export so ``from pipeline.economy import ...`` works.
"""

from .economic_viability import analyse, main  # noqa: F401
