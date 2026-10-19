"""Deterministic duty-definition policy: the project-type gated duty dimension set.

Why this module exists
----------------------
``schemas/duty.schema.json`` is a shared contract read by every project route, so its
``required`` list may not change (pure-increment rule: shared schemas may only gain
optional properties and enum values). The grease route therefore gets its extra
enforcement here, in the skill policy layer, gated on the upstream project type:

* ``PRECISION_GREASE_DEV`` -> the seven grease dimensions are required. Two of them are
  the lifeline (命门) dimensions named by the frozen plan: ``motion_regime`` (fretting
  wear, the core failure mode of a harmonic-drive flexspline) and ``torque_requirement``
  (grease hardening shows up as out-of-specification torque and is the number-one field
  complaint).
* any of the six oil project types -> the legacy seven dimensions, exactly as before:
  same required set, same order, same error strings.

The shared contract still lists the legacy seven in ``required``, so a grease-route
profile carries the legacy seven *and* the grease seven; both sets are enforced for that
route so the preflight verdict can never disagree with the schema verdict.

Provenance is not optional
--------------------------
``NO Provenance-Free Parameters`` is a pack red line: a dimension without ``source`` or
``evidence_id`` is a hard reject, never a warning. Per-dimension field checks live in one
shared helper so preflight, builder and validator cannot disagree about the same input.
"""

from __future__ import annotations

PRECISION_GREASE_PROJECT_TYPE = "PRECISION_GREASE_DEV"

# The six oil routes. Listed explicitly so the branch on project type is a lookup and
# never an implicit "anything that is not grease" default.
LEGACY_PROJECT_TYPES = (
    "NEW_PRODUCT",
    "IMPROVEMENT",
    "COST_DOWN",
    "CUSTOMIZATION",
    "EXPLORATION",
    "PROCESS_ROBUSTNESS",
)

LEGACY_DUTY_DIMENSIONS = (
    "equipment",
    "operating_conditions",
    "maintenance",
    "temperature",
    "load",
    "contamination",
    "life",
)

# The seven grease dimensions (refactor plan §3 step 2). The two lifelines carry their
# own error wording so a report can name exactly which 命门 dimension is missing.
GREASE_DUTY_DIMENSIONS = (
    "motion_regime",
    "contact_pair",
    "temperature_and_heat_source",
    "torque_requirement",
    "fill_and_assembly",
    "life_and_maintenance",
    "sealing_and_contamination",
)

GREASE_LIFELINE_DIMENSIONS = ("motion_regime", "torque_requirement")

DUTY_ITEM_TEXT_FIELDS = ("source", "evidence_id", "statement")
DUTY_ITEM_STATUSES = ("OBSERVED", "ASSUMED")


def has_text(value: object) -> bool:
    """True for a non-empty, non-blank string."""
    return isinstance(value, str) and bool(value.strip())


def has_value(value: object) -> bool:
    """True for a non-empty string or a real number (booleans are not values)."""
    return has_text(value) or isinstance(value, (int, float)) and not isinstance(value, bool)


def is_precision_grease(project_type: object) -> bool:
    """True only for the precision-gear grease route. An unknown type is not grease."""
    return project_type == PRECISION_GREASE_PROJECT_TYPE


def required_dimensions(project_type: object) -> tuple[str, ...]:
    """The dimension set THIS POLICY requires for one project type.

    Explicit branch: the grease route requires the grease seven, the six oil types
    require the legacy seven, and an absent/unknown type follows the legacy path so no
    oil behaviour can change by accident.
    """
    if is_precision_grease(project_type):
        return GREASE_DUTY_DIMENSIONS
    return LEGACY_DUTY_DIMENSIONS


def enforced_dimensions(project_type: object) -> tuple[str, ...]:
    """Every dimension the policy layer checks, in canonical storage order.

    The grease route enforces both sets: ``schemas/duty.schema.json`` still lists the
    legacy seven in ``required`` (the pure-increment rule forbids changing that), so
    requiring only the grease seven would let a profile pass this policy and then fail
    the schema check downstream. The oil routes enforce exactly the legacy seven.
    """
    if is_precision_grease(project_type):
        return LEGACY_DUTY_DIMENSIONS + GREASE_DUTY_DIMENSIONS
    return LEGACY_DUTY_DIMENSIONS


def carries_grease_dimensions(duty: object) -> bool:
    """True when a duty profile is grease-shaped (it records a grease dimension).

    The validator is handed the artifact alone and cannot read the upstream
    ``project.json``, so the presence of a grease dimension is its artifact-side signal
    for the grease route. The shared contract keeps those dimensions optional.
    """
    if not isinstance(duty, dict):
        return False
    return any(name in duty for name in GREASE_DUTY_DIMENSIONS)


def resolved_project_type(project_type: object, duty: object) -> object:
    """The project type to enforce for one call.

    An explicitly supplied project type always wins. Without one, a grease-shaped duty
    profile is enforced as the grease route: that direction can only ADD grease
    enforcement over an artifact that already declares grease dimensions, so an oil
    profile (no grease dimension) keeps its exact previous behaviour.
    """
    if isinstance(project_type, str) and project_type:
        return project_type
    if carries_grease_dimensions(duty):
        return PRECISION_GREASE_PROJECT_TYPE
    return None


def ordered_dimensions(duty: object, project_type: object) -> tuple[str, ...]:
    """The dimensions to record for this input, required set first.

    For a legacy input carrying the legacy seven this returns exactly the legacy seven in
    the legacy order, which is what the builder recorded before this policy existed. For
    a grease input every dimension is required, so it returns the canonical fourteen.
    """
    enforced = enforced_dimensions(project_type)
    presented = duty if isinstance(duty, dict) else {}
    extras = tuple(
        name
        for name in (LEGACY_DUTY_DIMENSIONS + GREASE_DUTY_DIMENSIONS)
        if name in presented and name not in enforced
    )
    return enforced + extras


def dimension_item_errors(item: object, label: str) -> list[str]:
    """Per-dimension checks shared by the preflight, the builder and the validator."""
    if not isinstance(item, dict):
        return [label]
    errors: list[str] = []
    if not has_value(item.get("value")):
        errors.append(f"{label}.value")
    for field in DUTY_ITEM_TEXT_FIELDS:
        if not has_text(item.get(field)):
            errors.append(f"{label}.{field}")
    if item.get("status") == "GAP":
        errors.append(f"{label}.status GAP requires resolution")
    elif item.get("status") not in DUTY_ITEM_STATUSES:
        errors.append(f"{label}.status must be OBSERVED or ASSUMED")
    return errors


def dimension_errors(duty: object, project_type: object) -> list[str]:
    """Required dimensions and per-dimension provenance, gated on the project type.

    Oil route: the legacy loop, in legacy order, with the legacy strings — byte-identical
    to the pre-policy preflight output.
    Grease route: the same checks over the legacy seven plus the grease seven, with the
    two lifeline dimensions reported with their own wording.
    """
    if not isinstance(duty, dict):
        return ["duty"]
    grease = is_precision_grease(project_type)
    errors: list[str] = []
    for name in enforced_dimensions(project_type):
        item = duty.get(name)
        label = f"duty.{name}"
        if not isinstance(item, dict):
            if grease and name in GREASE_LIFELINE_DIMENSIONS:
                errors.append(
                    f"{label} is a required lifeline (命门) dimension for {PRECISION_GREASE_PROJECT_TYPE}"
                )
            else:
                errors.append(label)
            continue
        errors.extend(dimension_item_errors(item, label))
    return errors


def policy_errors(duty: object, project_type: object) -> list[str]:
    """The full policy verdict for one duty profile under one project type."""
    return dimension_errors(duty, project_type)
