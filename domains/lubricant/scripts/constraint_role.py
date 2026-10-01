"""Single source of truth for design-space variable constraint roles.

A design-space variable participates in the mixture closure (`MIXTURE_CLOSED`)
or is an independent factor (`INDEPENDENT`). Because the two roles map onto two
different DOE channels, both the Stage 4 formulation preflight
(`skills/formulation-design/scripts/preflight_formulation_design.py`) and the
later DOE bridge preflight (`skills/doe-design/scripts/preflight_doe_design.py`,
WP-04a) must resolve the role through this one implementation. Writing a second
copy would recreate the double-list drift the plan explicitly forbids.

Resolution rule (V1.4):

    FORMULATION_VARIABLE               -> MIXTURE_CLOSED
    MATERIAL_FAMILY                    -> INDEPENDENT
    PROCESS_VARIABLE                   -> INDEPENDENT

An explicit `constraint_role` value wins only when it agrees with the derived
role; a contradictory declaration is rejected rather than silently accepted.
"""

from __future__ import annotations


CONSTRAINT_ROLES = ("MIXTURE_CLOSED", "INDEPENDENT")

# variable_type -> derived role. Unknown types raise ConstraintRoleError.
DERIVED_ROLE_BY_VARIABLE_TYPE = {
    "FORMULATION_VARIABLE": "MIXTURE_CLOSED",
    "MATERIAL_FAMILY": "INDEPENDENT",
    "PROCESS_VARIABLE": "INDEPENDENT",
}


class ConstraintRoleError(ValueError):
    """Raised when a variable type is unknown or a declared role contradicts it."""


def derive_constraint_role(variable_type: object) -> str:
    """Return the role implied by ``variable_type`` alone."""
    if not isinstance(variable_type, str) or variable_type not in DERIVED_ROLE_BY_VARIABLE_TYPE:
        raise ConstraintRoleError(
            f"unknown variable_type {variable_type!r}; expected one of {sorted(DERIVED_ROLE_BY_VARIABLE_TYPE)}"
        )
    return DERIVED_ROLE_BY_VARIABLE_TYPE[variable_type]


def resolve_constraint_role(variable_type: object, declared: object = None) -> str:
    """Return the effective constraint role for one variable.

    ``declared`` is the optional explicit value taken from the artifact. When it
    is absent the type-derived role is returned. When it is present it must be a
    valid enum member and must equal the derived role, otherwise a
    ``ConstraintRoleError`` is raised (no silent coercion).
    """
    derived = derive_constraint_role(variable_type)
    if declared is None:
        return derived
    if not isinstance(declared, str) or declared not in CONSTRAINT_ROLES:
        raise ConstraintRoleError(
            f"declared constraint_role {declared!r} is not one of {list(CONSTRAINT_ROLES)}"
        )
    if declared != derived:
        raise ConstraintRoleError(
            f"declared constraint_role {declared} contradicts variable_type {variable_type} (must be {derived})"
        )
    return declared


def describe_constraint_role(variable_type: object, declared: object = None) -> str:
    """Human-readable resolution line so a run is never silent about the role."""
    role = resolve_constraint_role(variable_type, declared)
    if declared is None:
        return f"CONSTRAINT_ROLE derived {role} from {variable_type}"
    return f"CONSTRAINT_ROLE declared {role} (consistent with {variable_type})"
