"""
services/theme_registry.py

Single source of truth for the GCAIP theme list.

Previously, three separate lists independently maintained the active-theme set:
  - services/orchestrator.py::ALL_THEMES
  - schemas/analysis.py::VALID_THEMES
  - gcaip-frontend/src/types/theme.ts::ACTIVE_THEMES (manually synced)

These could silently drift apart. This module is the canonical definition;
the other two now import from here. The frontend file must be kept in manual
sync (JavaScript cannot import Python modules) — a comment there points here.

Diagnostic report reference: Section 4, step 7.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ThemeSpec:
    """Metadata about one analysis theme."""
    id: str
    always_on: bool  # True = dispatch on every AOI; False = opt-in / gated by AOIClassifier


# ---- Theme registry ---------------------------------------------------------
# Order matters: it controls display order in the UI (THEME_ORDER in theme.ts
# mirrors this list). Add new themes at the end to avoid reordering existing UI.
THEME_REGISTRY: list[ThemeSpec] = [
    ThemeSpec("rainfall",           always_on=True),
    ThemeSpec("landuse",            always_on=True),
    ThemeSpec("effluent_plume",     always_on=False),   # gated: needs water body
    ThemeSpec("coastal_outfall",    always_on=False),   # gated: needs coastal water
    ThemeSpec("pipeline_corridor",  always_on=False),   # gated: needs pipeline nearby
]

# ---------------------------------------------------------------------------
# Derived helpers used by orchestrator.py and schemas/analysis.py
# ---------------------------------------------------------------------------

ALL_THEMES: list[str] = [t.id for t in THEME_REGISTRY]
"""All theme IDs in canonical order. orchestrator.py uses this as its default list."""

VALID_THEMES: list[str] = ALL_THEMES
"""Valid theme IDs for request validation. schemas/analysis.py uses this."""

ALWAYS_ON_THEMES: list[str] = [t.id for t in THEME_REGISTRY if t.always_on]
OPTIONAL_THEMES: list[str] = [t.id for t in THEME_REGISTRY if not t.always_on]
