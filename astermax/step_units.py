"""Conservative STEP Part 21 length-unit inspection for the AsterMax PMV.

AsterMax's verified numerical kernel uses mm-N-MPa.  STEP files can encode length
units inside complex entities such as::

    #42=(LENGTH_UNIT() NAMED_UNIT(*) SI_UNIT(.MILLI.,.METRE.));

This module intentionally does *not* rescale CAD silently.  It extracts explicit
SI length-unit declarations and provides a hard gate that accepts only millimetres.
Conversion-based units (for example inch) and ambiguous/missing declarations are
rejected so CAD preparation cannot drift by a hidden scale factor.
"""

from dataclasses import dataclass
import re


class StepUnitError(ValueError):
    """Raised when STEP length units are missing, ambiguous or unsupported."""


@dataclass(frozen=True)
class StepLengthUnit:
    name: str
    scale_to_mm: float
    entity: str


_ENTITY_RE = re.compile(r"#[0-9]+\s*=.*?;", re.IGNORECASE | re.DOTALL)
_SI_UNIT_RE = re.compile(
    r"SI_UNIT\s*\(\s*(\$|\.[A-Z_]+\.)\s*,\s*\.METRE\.\s*\)",
    re.IGNORECASE,
)

# ISO 10303 / SI prefixes that materially matter for CAD scale detection.
_PREFIX_TO_MM = {
    "$": ("m", 1000.0),
    ".MILLI.": ("mm", 1.0),
    ".CENTI.": ("cm", 10.0),
    ".DECI.": ("dm", 100.0),
    ".DECA.": ("dam", 10000.0),
    ".HECTO.": ("hm", 100000.0),
    ".KILO.": ("km", 1000000.0),
    ".MICRO.": ("um", 0.001),
}


def _normalized_entity(entity: str) -> str:
    return " ".join(entity.split())


def inspect_step_length_unit(text: str) -> StepLengthUnit:
    """Return the unique explicit SI length unit declared by a STEP Part 21 file.

    Only entities that contain both ``LENGTH_UNIT`` and an SI ``METRE`` unit are
    considered valid evidence.  Conversion-based length units are rejected rather
    than guessed because their conversion chain must be evaluated to establish scale.
    """
    entities = _ENTITY_RE.findall(text)
    if not entities:
        raise StepUnitError("STEP contains no parseable Part 21 entities")

    candidates: list[StepLengthUnit] = []
    conversion_based = []

    for entity in entities:
        upper = entity.upper()
        if "LENGTH_UNIT" not in upper:
            continue
        if "CONVERSION_BASED_UNIT" in upper:
            conversion_based.append(_normalized_entity(entity))
            continue

        match = _SI_UNIT_RE.search(entity)
        if not match:
            continue
        prefix = match.group(1).upper()
        if prefix not in _PREFIX_TO_MM:
            raise StepUnitError(f"unsupported SI length prefix in STEP: {prefix}")
        name, scale = _PREFIX_TO_MM[prefix]
        candidates.append(
            StepLengthUnit(name=name, scale_to_mm=scale, entity=_normalized_entity(entity))
        )

    if conversion_based and not candidates:
        raise StepUnitError(
            "STEP uses a conversion-based length unit; explicit conversion evaluation "
            "is required before AsterMax may mesh it"
        )
    if not candidates:
        raise StepUnitError("STEP has no explicit SI LENGTH_UNIT declaration")

    distinct = {(unit.name, unit.scale_to_mm) for unit in candidates}
    if len(distinct) != 1:
        summary = ", ".join(sorted(name for name, _ in distinct))
        raise StepUnitError(f"STEP declares ambiguous length units: {summary}")

    # Multiple identical declarations are common and harmless. Preserve one entity
    # as auditable evidence for the case record.
    return candidates[0]


def require_step_mm(text: str) -> StepLengthUnit:
    """Hard gate for the verified AsterMax mm-N-MPa analysis basis."""
    unit = inspect_step_length_unit(text)
    if unit.name != "mm" or unit.scale_to_mm != 1.0:
        raise StepUnitError(
            f"STEP length unit is {unit.name} (scale_to_mm={unit.scale_to_mm:g}); "
            "AsterMax requires an explicitly millimetre-resolved STEP before meshing"
        )
    return unit
