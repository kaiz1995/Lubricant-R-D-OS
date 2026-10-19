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

Grease extension (PRECISION_GREASE_DEV step 6, purely additive):

    material role REACTION_PRODUCT     -> INDEPENDENT (never MIXTURE_CLOSED)

Grease soap is generated in situ: fatty acid plus LiOH react during
saponification, so a "thickener percentage" is a PRODUCT of the batch, not a
charge. A 100 % mixture closure closes the CHARGE, and that constraint does not
hold for what determines the product, so a reaction-product variable must never
be routed into the mixture-closure channel. `CONSTRAINT_ROLES`, the three
`DERIVED_ROLE_BY_VARIABLE_TYPE` entries and both original functions are
unchanged: the extension takes an additional optional `material_role` argument
and caller code that omits it behaves exactly as before.
"""

from __future__ import annotations


CONSTRAINT_ROLES = ("MIXTURE_CLOSED", "INDEPENDENT")

# variable_type -> derived role. Unknown types raise ConstraintRoleError.
DERIVED_ROLE_BY_VARIABLE_TYPE = {
    "FORMULATION_VARIABLE": "MIXTURE_CLOSED",
    "MATERIAL_FAMILY": "INDEPENDENT",
    "PROCESS_VARIABLE": "INDEPENDENT",
}

# Material-side role of a design-space variable. INPUT_MATERIAL is a charge that
# is weighed into the kettle; REACTION_PRODUCT is a substance the batch is
# intended to CONTAIN, produced in situ by a reaction.
MATERIAL_ROLES = ("INPUT_MATERIAL", "REACTION_PRODUCT")

# The role every REACTION_PRODUCT variable resolves to. INDEPENDENT is the only
# role that can hold for a product target: it is not a charged fraction, so it
# never joins the charge-closure arithmetic.
REACTION_PRODUCT_CONSTRAINT_ROLE = "INDEPENDENT"

# Material categories whose content is generated in situ in a grease kettle
# rather than charged as such. A THICKENER_RAW material is the feedstock of the
# saponification reaction, so the substance a variable over that material
# actually ranges across is the SOAP the reaction produces - the plan's own
# "thickener system and soap concentration" variable. Its percentage is a
# product target, so it derives to the product side and never joins the
# charge closure (the plan's break-point B3: the soap is generated, a 100 %
# charge closure does not hold for what determines the product).
IN_SITU_PRODUCT_MATERIAL_CATEGORIES = ("THICKENER_RAW",)


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


def derive_variable_constraint_role(variable_type: object, material_role: object = None) -> str:
    """Return the role implied by ``variable_type`` plus the optional material role.

    ``material_role`` is the artifact's variable ``role`` value when one is
    declared (``INPUT_MATERIAL`` or ``REACTION_PRODUCT``). The argument is
    additive: omitting it returns exactly ``derive_constraint_role``.

    A ``REACTION_PRODUCT`` variable resolves to ``INDEPENDENT`` whatever its
    ``variable_type`` says. The reason is the in-situ reaction: the soap is
    generated during saponification, so its percentage is a product target and
    not a charged fraction, and a ``MIXTURE_CLOSED`` classification would put a
    reaction product into the charge-closure arithmetic where it does not
    belong.
    """
    if material_role is None:
        return derive_constraint_role(variable_type)
    if material_role not in MATERIAL_ROLES:
        raise ConstraintRoleError(
            f"material role {material_role!r} is not one of {list(MATERIAL_ROLES)}"
        )
    # Validate the type first so an unknown type is still reported as such.
    derive_constraint_role(variable_type)
    if material_role == "REACTION_PRODUCT":
        return REACTION_PRODUCT_CONSTRAINT_ROLE
    return derive_constraint_role(variable_type)


def resolve_variable_constraint_role(variable_type: object, declared: object = None, material_role: object = None) -> str:
    """Return the effective constraint role for one variable, honouring ``role``.

    Extends :func:`resolve_constraint_role` with the material-side ``role``. With
    ``material_role`` omitted the result is identical to the pre-extension rule,
    so existing callers are unaffected.

    A ``REACTION_PRODUCT`` variable is never ``MIXTURE_CLOSED``: an explicit
    ``MIXTURE_CLOSED`` declaration is rejected with the semantic reason spelled
    out, so a caller cannot mistake it for a typo.
    """
    derived = derive_variable_constraint_role(variable_type, material_role)
    if declared is None:
        return derived
    if not isinstance(declared, str) or declared not in CONSTRAINT_ROLES:
        raise ConstraintRoleError(
            f"declared constraint_role {declared!r} is not one of {list(CONSTRAINT_ROLES)}"
        )
    if material_role == "REACTION_PRODUCT" and declared == "MIXTURE_CLOSED":
        raise ConstraintRoleError(
            "declared constraint_role MIXTURE_CLOSED contradicts material role REACTION_PRODUCT: "
            "a substance generated in situ is a product of the reaction, not a charged input, so it "
            "must never join the mixture closure of the charge"
        )
    if declared != derived:
        suffix = f" (must be {derived})"
        if material_role == "REACTION_PRODUCT":
            suffix = f" (must be {derived}: a REACTION_PRODUCT is never MIXTURE_CLOSED)"
        raise ConstraintRoleError(
            f"declared constraint_role {declared} contradicts variable_type {variable_type}{suffix}"
        )
    return declared


def describe_variable_constraint_role(variable_type: object, declared: object = None, material_role: object = None) -> str:
    """Human-readable resolution line for the extended (material-role aware) rule."""
    role = resolve_variable_constraint_role(variable_type, declared, material_role)
    if declared is not None:
        return f"CONSTRAINT_ROLE declared {role} (consistent with {variable_type})"
    if material_role == "REACTION_PRODUCT":
        return f"CONSTRAINT_ROLE derived {role} from material role REACTION_PRODUCT (in-situ product, never MIXTURE_CLOSED)"
    return f"CONSTRAINT_ROLE derived {role} from {variable_type}"
