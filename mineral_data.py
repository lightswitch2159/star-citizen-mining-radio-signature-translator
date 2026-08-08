"""
Resource Signature (RS) reference data for Star Citizen mining, and the
matching logic used to turn an OCR'd number into a mineral name.

Base values below are the "multiple 1" RS reading for each mineral, taken
from the community reference sheet. The in-game reading scales linearly
with node richness, i.e. reading == base * multiple, for multiple 1-7.

`co_occurs_with` is the mineral the sheet lists alongside each entry --
that's a rock the primary mineral is often physically found together with
in the same node, not an alternative/confusable RS signature. It's purely
informational (may also be minable from the same rock) and has no role in
matching -- it's not used to disambiguate or score readings.

Salvage/scrap nodes read as a clean multiple of 2000 (2000, 4000, 6000...)
at any multiplier, independent of the mineral table above. Since that can
land exactly on top of a real mineral's value, a reading that's both a
mineral match and a multiple of 2000 is reported as "Salvage/{mineral}"
rather than silently picking one.
"""

from dataclasses import dataclass, field
from typing import Optional

# (primary name, mineral commonly co-occurring in the same node, base RS value at multiple 1)
_RAW_TABLE = [
    ("Quantanium",   "Beryl",                 3170),
    ("Stileron",     "Taranite",              3185),
    ("Savrilium",    "Gold",                  3200),
    ("Ouratite",     "Agricium",              3370),
    ("Riccite",      "Laranite",              3385),
    ("Lindinium",    "Tungsten",              3400),
    ("Beryl",        None,                    3540),
    ("Taranite",     None,                    3555),
    ("Borase",       "Bexalite/Gold",         3570),
    ("Gold",         "Bexalite/Borase",       3585),
    ("Bexalite",     "Gold/Borase",           3600),
    ("Laranite",     "Tungsten",              3825),
    ("Aslarite",     "Agricium/Titanium",     3840),
    ("Titanium",     "Aslarite/Agricium",     3855),
    ("Tungsten",     "Laranite",              3870),
    ("Agricium",     "Aslarite/Titanium",     3885),
    ("Torite",       None,                    3900),
    ("Hephestanite", "Raw Silicon/Quartz",    4180),
    ("Tin",          "Copper",                4195),
    ("Quartz",       "Hephestanite/Silicon",  4210),
    ("Corundum",     "Aluminum",              4225),
    ("Copper",       "Tin",                   4240),
    ("Silicon",      "Hephestanite/Quartz",   4255),
    ("Iron",         None,                    4270),
    ("Aluminum",     "Corundum",              4285),
    ("Ice",          None,                    4300),
]

MAX_MULTIPLE = 7
SALVAGE_STEP = 2000
# Real RS readings top out well under 2000*20 -- cap how far we'll extrapolate
# the salvage multiple so OCR garbage (e.g. a stray extra digit) can't get
# rounded into a bogus "Salvage" match.
MAX_SALVAGE_MULTIPLE = 20

# Rarity tier per mineral, for color-coding the result in the UI.
#
# NOT sourced from the same community reference sheet as the RS base values
# above -- this is a best-effort tier assignment from general Star Citizen
# community knowledge, filled in without access to the user's sheet or a
# live game client to verify against. SC rebalances rarity/availability
# periodically. Treat this as a reasonable starting point, not ground
# truth -- if it disagrees with what you see in-game, this table is what's
# wrong; fix the entries below rather than the lookup/display code.
RARITY_COMMON = "Common"
RARITY_UNCOMMON = "Uncommon"
RARITY_RARE = "Rare"
RARITY_VERY_RARE = "Very Rare"
RARITY_ULTRA_RARE = "Ultra Rare"
RARITY_SALVAGE = "Salvage"

RARITY_COLORS = {
    RARITY_COMMON: "#9a9a9a",
    RARITY_UNCOMMON: "#2e9e44",
    RARITY_RARE: "#2f7de1",
    RARITY_VERY_RARE: "#9b4fd6",
    RARITY_ULTRA_RARE: "#e0982a",
    RARITY_SALVAGE: "#5f7a8a",
}

_RARITY_BY_MINERAL = {
    "Quartz": RARITY_COMMON,
    "Hephestanite": RARITY_COMMON,
    "Corundum": RARITY_COMMON,
    "Iron": RARITY_COMMON,
    "Copper": RARITY_COMMON,
    "Tin": RARITY_COMMON,
    "Aluminum": RARITY_COMMON,
    "Silicon": RARITY_COMMON,
    "Ice": RARITY_COMMON,
    "Torite": RARITY_UNCOMMON,
    "Laranite": RARITY_UNCOMMON,
    "Titanium": RARITY_UNCOMMON,
    "Tungsten": RARITY_UNCOMMON,
    "Agricium": RARITY_UNCOMMON,
    "Aslarite": RARITY_RARE,
    "Gold": RARITY_RARE,
    "Bexalite": RARITY_RARE,
    "Borase": RARITY_RARE,
    "Ouratite": RARITY_RARE,
    "Lindinium": RARITY_RARE,
    "Beryl": RARITY_RARE,
    "Taranite": RARITY_VERY_RARE,
    "Stileron": RARITY_VERY_RARE,
    "Riccite": RARITY_VERY_RARE,
    "Savrilium": RARITY_VERY_RARE,
    "Quantanium": RARITY_ULTRA_RARE,
}


def rarity_of(mineral_name: str) -> Optional[str]:
    """
    Rarity tier for a mineral/candidate name, for UI color-coding.

    Handles the "Salvage/{mineral}" combo names lookup_rs() produces (see
    module docstring) by looking up the underlying mineral -- a salvage
    node that happens to also be a Quantanium reading is still shown as
    Quantanium-rare, not lumped in with plain scrap. Plain "Salvage" (no
    mineral match) gets its own neutral tier.
    """
    if mineral_name == "Salvage":
        return RARITY_SALVAGE
    base = mineral_name.split("/", 1)[1] if mineral_name.startswith("Salvage/") else mineral_name
    return _RARITY_BY_MINERAL.get(base)


@dataclass
class Candidate:
    mineral: str
    co_occurs_with: Optional[str]
    multiple: int
    value: int
    diff: int
    rel_error: float


@dataclass
class LookupResult:
    status: str  # "match" | "ambiguous" | "unknown"
    query: int
    candidates: list = field(default_factory=list)

    @property
    def best(self) -> Optional[Candidate]:
        return self.candidates[0] if self.candidates else None


def _build_table():
    entries = []
    for name, co_occurs_with, base in _RAW_TABLE:
        for multiple in range(1, MAX_MULTIPLE + 1):
            entries.append((name, co_occurs_with, multiple, base * multiple))
    return entries


_TABLE = _build_table()


def _score_minerals(value: int):
    scored = []
    for name, co_occurs_with, multiple, table_value in _TABLE:
        diff = abs(table_value - value)
        rel_error = diff / table_value
        scored.append(
            Candidate(
                mineral=name,
                co_occurs_with=co_occurs_with,
                multiple=multiple,
                value=table_value,
                diff=diff,
                rel_error=rel_error,
            )
        )
    scored.sort(key=lambda c: (c.rel_error, c.diff))
    return scored


def _lookup_mineral_only(value: int, tight_rel_tol: float, loose_rel_tol: float, max_candidates: int) -> LookupResult:
    scored = _score_minerals(value)
    if not scored:
        return LookupResult(status="unknown", query=value)

    best = scored[0]

    if best.rel_error <= tight_rel_tol:
        seen = set()
        top = []
        for c in scored:
            if c.rel_error > tight_rel_tol:
                break
            if c.mineral not in seen:
                seen.add(c.mineral)
                top.append(c)
        return LookupResult(status="match", query=value, candidates=top[:max_candidates])

    if best.rel_error <= loose_rel_tol:
        seen = set()
        top = []
        for c in scored:
            if c.rel_error > loose_rel_tol:
                break
            if c.mineral not in seen:
                seen.add(c.mineral)
                top.append(c)
            if len(top) >= max_candidates:
                break
        return LookupResult(status="ambiguous", query=value, candidates=top)

    return LookupResult(status="unknown", query=value)


def _salvage_candidate(value: int):
    """
    Return (Candidate, rel_error) for the nearest multiple of SALVAGE_STEP,
    or (None, None) if value is non-positive.
    """
    if value <= 0:
        return None, None
    n = round(value / SALVAGE_STEP) or 1
    if n > MAX_SALVAGE_MULTIPLE:
        return None, None
    nearest = n * SALVAGE_STEP
    diff = abs(nearest - value)
    rel_error = diff / nearest
    candidate = Candidate(
        mineral="Salvage",
        co_occurs_with=None,
        multiple=n,
        value=nearest,
        diff=diff,
        rel_error=rel_error,
    )
    return candidate, rel_error


def lookup_rs(
    value: int,
    tight_rel_tol: float = 0.0025,
    loose_rel_tol: float = 0.02,
    max_candidates: int = 3,
) -> LookupResult:
    """
    Match a raw RS reading against the reference table.

    - Exact or near-exact (within tight_rel_tol) hits are returned as a
      confident single "match".
    - Hits only within loose_rel_tol are returned as "ambiguous" with up to
      max_candidates ranked options -- this happens when two *different*
      minerals' RS values genuinely sit close together numerically (e.g.
      Borase/Gold/Bexalite, only ~15 apart), or from OCR noise. This is
      unrelated to `co_occurs_with`, which is just informational.
    - Nothing within loose_rel_tol is "unknown".
    - Salvage/scrap nodes read as any multiple of 2000. If a reading is
      both a mineral match and a salvage multiple, candidates are labeled
      "Salvage/{mineral}" instead of picking one silently. If it's only a
      salvage multiple (no mineral match), it's reported as plain "Salvage".
    """
    if value <= 0:
        return LookupResult(status="unknown", query=value)

    mineral_result = _lookup_mineral_only(value, tight_rel_tol, loose_rel_tol, max_candidates)
    salvage_candidate, salvage_rel_error = _salvage_candidate(value)
    salvage_tight = salvage_rel_error is not None and salvage_rel_error <= tight_rel_tol
    salvage_loose = salvage_rel_error is not None and salvage_rel_error <= loose_rel_tol

    if mineral_result.status in ("match", "ambiguous"):
        if salvage_tight:
            for c in mineral_result.candidates:
                c.mineral = f"Salvage/{c.mineral}"
        return mineral_result

    # No mineral match at all -- fall back to salvage-only.
    if salvage_tight:
        return LookupResult(status="match", query=value, candidates=[salvage_candidate])
    if salvage_loose:
        return LookupResult(status="ambiguous", query=value, candidates=[salvage_candidate])

    return LookupResult(status="unknown", query=value)


if __name__ == "__main__":
    # quick sanity checks
    for v in [3170, 6400, 3600, 3585, 3570, 2000, 8000, 8570, 9999999, 1]:
        r = lookup_rs(v)
        print(v, "->", r.status, [(c.mineral, c.value) for c in r.candidates])
