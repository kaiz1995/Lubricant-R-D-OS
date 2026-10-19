"""Deterministic Stage 4 design-space decision policy shared by builder and validator.

The grease route (PRECISION_GREASE_DEV, outer-loop step 6) adds four mandatory
elements that the six oil routes do not have today. They are gated on the
upstream ``project_type`` so the oil routes keep their current behaviour
byte-for-byte:

1. Every material-bearing variable must reference a ``material`` object, and the
   referenced ``material_id`` must resolve to a readable material record. A bare
   name string is not a material: without the object there is no supplier, lot,
   chemistry family, or property list, so the variable cannot be compared or
   reproduced.

2. ``baseline_process_reference`` is required. If the process changed, comparing
   formulae is invalid: two fraction lists run over different kettle settings are
   not the same experiment.

3. Every variable must declare its material-side ``role`` (charge or product) and
   must carry a ``constraint_rationale``. The rationale is enforced for every
   route by the shared contract; the role is the grease addition, because step 6
   has to say which variables are charges and which are reaction products.

4. The IN-SITU REACTION SEMANTICS. Grease soap is generated during
   saponification, so a thickener percentage is a product of the batch and not a
   charge: a 100 % mixture closure closes the CHARGE, and that constraint does
   not hold for what determines the product. A ``REACTION_PRODUCT`` variable is
   therefore never ``MIXTURE_CLOSED``, and a formulation variable over an in-situ
   feedstock may not be declared as a charged input.
"""

from __future__ import annotations


GREASE_PROJECT_TYPE = "PRECISION_GREASE_DEV"

# Variable types that range over a material, so the grease route requires them to
# reference a material object. A PROCESS_VARIABLE ranges over the kettle, not a
# material, so it is exempt.
MATERIAL_BEARING_VARIABLE_TYPES = ("MATERIAL_FAMILY", "FORMULATION_VARIABLE")

# The two declared material roles.
INPUT_MATERIAL = "INPUT_MATERIAL"
REACTION_PRODUCT = "REACTION_PRODUCT"
MATERIAL_ROLES = (INPUT_MATERIAL, REACTION_PRODUCT)

# Material categories whose content is generated in situ rather than charged as
# such. A THICKENER_RAW material is the saponification feedstock (fatty acid /
# alkali), and the substance that determines the product is the SOAP the
# reaction produces from it, so a formulation variable over that material is a
# product target.
IN_SITU_PRODUCT_MATERIAL_CATEGORIES = ("THICKENER_RAW",)

# Fields whose presence marks an artifact as using the grease extension. The
# validator has no project.json path, so it detects the route from the artifact
# itself: a record that uses the extension must satisfy the whole extension.
GREASE_EXTENSION_DESIGN_SPACE_FIELDS = ("baseline_process_reference", "feasibility_regions")

FEASIBILITY_CONVEXITIES = ("CONVEX", "NON_CONVEX")
CONSTRAINT_KINDS = ("BOUND", "MIXTURE_CLOSURE_INPUTS", "FEASIBILITY_STRUCTURAL")

# Advisory, never a HOLD: the closure the space actually uses should be named.
MIXTURE_CLOSURE_KIND = "MIXTURE_CLOSURE_INPUTS"


def has_text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def is_grease_route(project_type: object) -> bool:
    """True when the supplied upstream project type carries the grease rules."""
    return project_type == GREASE_PROJECT_TYPE


def carries_grease_extension(design_space: object) -> bool:
    """True when a design space uses any grease-only field.

    Used by the validator, which sees only the artifact. A record that uses the
    extension is held to the whole extension rather than to the part it declared.
    """
    if not isinstance(design_space, dict):
        return False
    if any(field in design_space for field in GREASE_EXTENSION_DESIGN_SPACE_FIELDS):
        return True
    variables = design_space.get("variables")
    if not isinstance(variables, list):
        return False
    return any(
        isinstance(variable, dict) and ("material_reference" in variable or "role" in variable)
        for variable in variables
    )


def effective_route_is_grease(project_type: object, design_space: object = None) -> bool:
    """Grease rules apply when the upstream route says so or the record uses them."""
    return is_grease_route(project_type) or carries_grease_extension(design_space)


def has_gap(design_space: dict) -> bool:
    evidence = design_space.get("evidence")
    return isinstance(evidence, list) and any(isinstance(item, dict) and item.get("status") == "GAP" for item in evidence)


def derive_material_role(material_category: object) -> str | None:
    """Material role implied by a material's category, or None when unknown.

    Returns ``REACTION_PRODUCT`` for an in-situ feedstock (its soap is generated
    in the kettle) and ``INPUT_MATERIAL`` for everything else. An absent or
    unrecognised category yields None: the policy reports what it can prove and
    never invents a classification.
    """
    if not has_text(material_category):
        return None
    return REACTION_PRODUCT if material_category in IN_SITU_PRODUCT_MATERIAL_CATEGORIES else INPUT_MATERIAL


def feasibility_region_errors(region: object, label: str) -> list[str]:
    """Structural checks for one declared feasible region."""
    if not isinstance(region, dict):
        return [label]
    permitted = {"region_id", "expression", "convexity", "connected", "rationale", "evidence_id"}
    errors = [f"{label}.{field} is not a permitted feasible-region field" for field in sorted(set(region) - permitted)]
    for field in ("region_id", "expression", "rationale"):
        if not has_text(region.get(field)):
            errors.append(f"{label}.{field}")
    if region.get("convexity") not in FEASIBILITY_CONVEXITIES:
        errors.append(f"{label}.convexity must be one of {list(FEASIBILITY_CONVEXITIES)}")
    if not isinstance(region.get("connected"), bool):
        errors.append(f"{label}.connected")
    return errors


def grease_notes(design_space: object) -> list[str]:
    """Advisory lines about the closure basis. Never a HOLD."""
    if not isinstance(design_space, dict):
        return []
    constraints = design_space.get("constraints")
    if not isinstance(constraints, list):
        return []
    kinds = {item.get("kind") for item in constraints if isinstance(item, dict)}
    closed_charges = [
        variable.get("variable_id")
        for variable in design_space.get("variables", [])
        if isinstance(variable, dict) and variable.get("constraint_role") == "MIXTURE_CLOSED"
    ]
    if closed_charges and MIXTURE_CLOSURE_KIND not in kinds:
        return [
            "NOTE: variables "
            f"{sorted(closed_charges)} resolve to MIXTURE_CLOSED but no {MIXTURE_CLOSURE_KIND} constraint is declared; "
            "state which side the closure applies to, because a 100 % closure of the charge does not hold for what determines the product"
        ]
    if MIXTURE_CLOSURE_KIND in kinds:
        return [f"NOTE: closure basis declared as {MIXTURE_CLOSURE_KIND} (closes the CHARGE, not the product composition)"]
    return []


def expected_decision_fields(design_space: dict, project_type: object = None) -> dict[str, str]:
    """Canonical decision block. Route-independent so builder and validator agree.

    The grease requirements are enforced fail-closed in the preflight and again in
    the validator's semantic checks; they deliberately do not fork the decision
    text, because the validator sees the artifact without its upstream charter and
    two different rule strings would make the same record pass or fail depending
    on which side recomputed it.
    """
    design_space_id = design_space.get("design_space_id", "")
    ready = not has_gap(design_space)
    return {
        "decision_question": f"Is the supplied input sufficient to define testable design space {design_space_id}?",
        "hypothesis": f"{design_space_id} records supplied variables, bounds, constraints, CTQ links, and qualified-method links sufficient for later testing.",
        "uncertainty": "Supplied bounds, constraints, sources, and provenance are not independently verified; recorded ASSUMED evidence remains assumed and this record does not establish formula, experiment, performance, cost, or optimization conclusions.",
        "decision_rule": "Define the design space only when upstream links, complete bound metadata, ordered same-unit bounds, constraints, and evidence without GAP are supplied.",
        "result": f"{design_space_id} is {'sufficient' if ready else 'not sufficient'} to define a testable design space from supplied input only.",
        "decision": "GO" if ready else "HOLD",
        "next_action": f"Retain {design_space_id} as the supplied design-space record." if ready else "Retain the supplied evidence and resolve the recorded GAP before defining a design space.",
    }
