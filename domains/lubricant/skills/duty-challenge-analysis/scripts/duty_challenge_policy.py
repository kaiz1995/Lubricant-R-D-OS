"""Deterministic duty/challenge policy: the project-type gated challenge category set.

Why this module exists
----------------------
``schemas/challenge.schema.json`` is a shared contract, so its ``category`` enum may only
GAIN values (pure-increment rule: shared schemas may only gain optional properties and enum
values). The grease route therefore cannot have the three oil-only values removed from the
contract; that rejection lives here instead, gated on the project type:

* ``PRECISION_GREASE_DEV`` -> ``WATER_CONTAMINATION`` / ``AIR_FOAM`` / ``MIXING`` are
  rejected because they name no grease challenge: a grease has no foam reservoir and no sump
  oil to mix, and water ingress into a sealed precision reducer reduces to sealing
  integrity. The route carries the eight grease challenges instead: fretting wear, thin-film
  EP, low-temperature torque, shear stability, soap fiber structure, interface
  compatibility, high-temperature oil separation and evaporation.
* any of the six oil project types -> the twelve original values, unchanged, including the
  three above.

How the project type is resolved
--------------------------------
The upstream of this skill is the duty artifact, which records ``project_reference`` (an id,
not a type). Two signals are therefore accepted, strongest first:

1. an explicit ``project_artifact`` on the input (the same shape the project-definition and
   failure-ctq preflights already accept) - read its ``project_type``;
2. otherwise, the shape of the validated duty artifact: a duty profile that records a
   dimension outside the legacy seven is a non-oil route, because only the grease route has
   such dimensions.

Both signals can only ever ADD grease enforcement over an input that is already
grease-shaped; an oil input resolves to the legacy path and behaves exactly as before.
"""

from __future__ import annotations

import json
from pathlib import Path

PRECISION_GREASE_PROJECT_TYPE = "PRECISION_GREASE_DEV"

LEGACY_PROJECT_TYPES = (
    "NEW_PRODUCT",
    "IMPROVEMENT",
    "COST_DOWN",
    "CUSTOMIZATION",
    "EXPLORATION",
    "PROCESS_ROBUSTNESS",
)

# Fallback only: the real source of truth for the legacy dimension set is the
# ``required`` list of ``duty.schema.json``, which this skill installs beside its scripts
# (``SKILLS["duty-challenge-analysis"]`` ships duty.schema.json). Reading the deployed
# schema keeps one source of truth and needs no cross-skill import, which a deployed
# bundle could not resolve; this frozen tuple is used only when the schema is unreachable.
FALLBACK_LEGACY_DUTY_DIMENSIONS = (
    "equipment",
    "operating_conditions",
    "maintenance",
    "temperature",
    "load",
    "contamination",
    "life",
)

# The twelve original oil-route categories. Frozen: oil-route behaviour must not change.
LEGACY_CHALLENGE_CATEGORIES = (
    "MECHANICAL_LOAD",
    "CONTACT",
    "HIGH_TEMPERATURE",
    "LOW_TEMPERATURE",
    "OXIDATION",
    "WATER_CONTAMINATION",
    "AIR_FOAM",
    "PARTICLE_CONTAMINATION",
    "MATERIAL_COMPATIBILITY",
    "LONG_TERM_STABILITY",
    "MIXING",
    "RAW_MATERIAL_VARIATION",
)

# The eight grease challenges added by the refactor plan §3 step 3.
GREASE_CHALLENGE_CATEGORIES = (
    "FRETTING_WEAR",
    "THIN_FILM_EP",
    "LOW_TEMP_TORQUE",
    "SHEAR_STABILITY",
    "SOAP_FIBER_STRUCTURE",
    "INTERFACE_COMPATIBILITY",
    "HIGH_TEMP_OIL_SEPARATION",
    "EVAPORATION",
)

# The three oil-only categories the grease route rejects. They stay schema-legal (the
# pure-increment rule forbids removing enum values) and stay valid for every oil route.
OIL_ONLY_CHALLENGE_CATEGORIES = (
    "WATER_CONTAMINATION",
    "AIR_FOAM",
    "MIXING",
)

ALL_CHALLENGE_CATEGORIES = LEGACY_CHALLENGE_CATEGORIES + GREASE_CHALLENGE_CATEGORIES
LEVELS = ("LOW", "MEDIUM", "HIGH")
CHALLENGE_FIELDS = (
    "duty_reference", "challenge_id", "category", "description", "severity",
    "exposure", "lubricant_sensitivity", "evidence_gap", "priority",
)
EVIDENCE_FIELDS = ("evidence_id", "statement", "source")

SKILL_ROOT = Path(__file__).resolve().parents[1]


def has_text(value: object) -> bool:
    """True for a non-empty, non-blank string."""
    return isinstance(value, str) and bool(value.strip())


def schema_dir() -> Path:
    """Canonical pack schemas when present, else the deployed ``references/`` copies."""
    canonical = SKILL_ROOT.parents[1] / "schemas"
    if all((canonical / name).is_file() for name in ("common.schema.json", "duty.schema.json")):
        return canonical
    return SKILL_ROOT / "references"


def legacy_duty_dimensions() -> tuple[str, ...]:
    """The legacy seven, read from the duty contract's own ``required`` list."""
    try:
        schema = json.loads((schema_dir() / "duty.schema.json").read_text(encoding="utf-8"))
        required = schema["properties"]["duty"]["required"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError):
        return FALLBACK_LEGACY_DUTY_DIMENSIONS
    if not isinstance(required, list) or not required or not all(has_text(name) for name in required):
        return FALLBACK_LEGACY_DUTY_DIMENSIONS
    return tuple(required)


def is_precision_grease(project_type: object) -> bool:
    """True only for the precision-gear grease route. An unknown type is not grease."""
    return project_type == PRECISION_GREASE_PROJECT_TYPE


def duty_is_grease_shaped(duty: object) -> bool:
    """True when a validated duty profile records a dimension beyond the legacy seven.

    Only the grease route has such dimensions, so this is the artifact-side signal that
    the upstream route is the precision-gear grease route.
    """
    if not isinstance(duty, dict):
        return False
    legacy = legacy_duty_dimensions()
    return any(name not in legacy for name in duty)


def resolved_project_type(project_artifact: object, duty_artifact: object) -> object:
    """The project type to enforce for this input, or None when it is not determinable.

    An explicit upstream project charter wins; without one, a grease-shaped duty artifact
    is enforced as the grease route. None means the legacy path, which is what every oil
    input resolves to.
    """
    if isinstance(project_artifact, dict) and has_text(project_artifact.get("project_type")):
        return project_artifact["project_type"]
    duty = duty_artifact.get("duty") if isinstance(duty_artifact, dict) else None
    if duty_is_grease_shaped(duty):
        return PRECISION_GREASE_PROJECT_TYPE
    return None


def allowed_categories(project_type: object) -> tuple[str, ...]:
    """Categories the policy layer accepts for one project type.

    The shared enum is the authority for membership on every route except the grease route,
    where the policy ADDS exactly one restriction (the three oil-only values). This is the
    pure-increment shape the pack requires: the eight grease values were APPENDED to the
    shared enum, so they are legal wherever the enum is; no oil route gains a new rejection,
    and every legacy twelve stay accepted.
    """
    if is_precision_grease(project_type):
        return tuple(
            name for name in ALL_CHALLENGE_CATEGORIES if name not in OIL_ONLY_CHALLENGE_CATEGORIES
        )
    return ALL_CHALLENGE_CATEGORIES


def category_errors(category: object, project_type: object) -> list[str]:
    """Category validity for one project type.

    Unknown value on any route: ``challenge.category is invalid``, the same string the
    pre-policy preflight produced for the twelve legacy values. Grease route: the three
    oil-only values get a distinct message naming the offending category and the
    superseding grease challenge. Oil routes: unchanged, no new restriction.
    """
    if is_precision_grease(project_type) and category in OIL_ONLY_CHALLENGE_CATEGORIES:
        return [
            f"challenge.category {category} names no grease challenge "
            f"(oil-only value rejected for {PRECISION_GREASE_PROJECT_TYPE}; "
            "use INTERFACE_COMPATIBILITY for sealing or media ingress)"
        ]
    if category not in allowed_categories(project_type):
        return ["challenge.category is invalid"]
    return []


def resolved_path(value: object, input_path: Path) -> Path | None:
    """Resolve an input-declared path against the input file's own directory."""
    if not has_text(value):
        return None
    path = Path(value)
    return path if path.is_absolute() else input_path.parent / path
