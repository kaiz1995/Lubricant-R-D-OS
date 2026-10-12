"""Deterministic knowledge-archive policy: the six-asset closure rule.

Step 17 (knowledge-archive) closes a project by landing the six knowledge assets the
redesign names - recommended formula, feasible design space, critical failure
boundaries, evidence package, material knowledge, model - as one ``knowledge_asset``
artifact at ``KNOWLEDGE_ARCHIVED``. Before this skill existed the schema had no producer
at all, so the retrieval index was permanently empty; this module is the single place
where the closure status is judged, and it is shared by the preflight, the builder, and
the validator so the three scripts cannot disagree.

Three rules, all fail-closed:

1. THE STATUS IS DERIVED, NOT CLAIMED. ``CLOSED_KNOWLEDGE`` is legal only when all six
   assets are present AND the evidence package is present and QUALIFIED. Anything short
   of that caps the record at ``DRAFT_KNOWLEDGE``. The builder downgrades a larger claim
   (it never upgrades one), and the validator re-derives the rule from the frozen
   artifact, so a hand edit cannot turn five assets plus a promise into a closed record.
   Stated boundary: a DRAFT record with all six assets present is legal - draft is always
   the safe direction - and the validator accepts it as long as the CLOSED case stays
   inside the rule.

2. A SYNTHETIC PROJECT CAN NEVER CLOSE. Synthetic evidence caps the record at
   ``DRAFT_KNOWLEDGE`` and force-marks it ``SYNTHETIC_DEMO_ONLY`` (red line NO Synthetic
   Closure). The marker is derived from the evidence scope, never supplied.

3. COST NEVER ENTERS A CTQ CRITERION (redesign section 6.3). Cost is a constraint
   (step 6 filter / step 14 constraint / step 16 ceiling check), never a criterion, and a
   knowledge record that archived a cost criterion would freeze that error into reuse.
   The archive therefore refuses an asset reference that declares itself a cost CTQ:
   the identity must not read as a cost criterion (``CTQ-COST``-style or a cost keyword),
   because the correct place for cost is the cost ceiling, not the criteria chain.
"""

from __future__ import annotations


ASSET_KEYS = (
    "recommended_formula",
    "feasible_design_space",
    "critical_failure_boundaries",
    "evidence_package",
    "material_knowledge",
    "model",
)
QUALIFIED_ASSET_KEY = "evidence_package"
QUALIFICATION_VALUES = ("QUALIFIED", "PROVISIONAL", "UNQUALIFIED")
ASSET_STATUSES = ("DRAFT_KNOWLEDGE", "CLOSED_KNOWLEDGE")
EVIDENCE_SCOPES = ("SYNTHETIC", "PHYSICAL")
EVIDENCE_STATUSES = ("OBSERVED", "ASSUMED", "GAP")
SYNTHETIC_MARKER = "SYNTHETIC_DEMO_ONLY"
STAGE = "KNOWLEDGE_ARCHIVED"
ASSET_ENTRY_FIELDS = {"artifact_reference", "present"}
QUALIFIED_ASSET_FIELDS = {"artifact_reference", "present", "qualification_reference", "qualification"}
INPUT_FIELDS = {"project_artifact", "asset_status", "knowledge_assets", "evidence_scope", "evidence"}
# Cost-as-CTQ detection: an identity token check, deliberately narrow so it never
# fires on an ordinary criterion. It looks for a cost term inside a CTQ identity.
COST_TERMS = ("COST", "COST_TARGET", "价格", "成本", "PRICE")
STAGE_CONSTANT_IN_PROJECT = "PROJECT_DEFINED"


def has_text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def has_gap(container: dict) -> bool:
    evidence = container.get("evidence")
    return isinstance(evidence, list) and any(
        isinstance(item, dict) and item.get("status") == "GAP" for item in evidence
    )


def asset_entries(value: object) -> dict:
    """The ``knowledge_assets`` block as a plain mapping (empty when malformed)."""
    return value if isinstance(value, dict) else {}


def present_keys(knowledge_assets: object) -> list[str]:
    """The six asset keys recorded ``present: true``, in canonical order."""
    assets = asset_entries(knowledge_assets)
    return [key for key in ASSET_KEYS if isinstance(assets.get(key), dict) and assets[key].get("present") is True]


def missing_keys(knowledge_assets: object) -> list[str]:
    """The six asset keys NOT recorded ``present: true``, in canonical order."""
    present = set(present_keys(knowledge_assets))
    return [key for key in ASSET_KEYS if key not in present]


def evidence_package_qualified(knowledge_assets: object) -> bool:
    package = asset_entries(knowledge_assets).get(QUALIFIED_ASSET_KEY)
    return (
        isinstance(package, dict)
        and package.get("present") is True
        and package.get("qualification") == "QUALIFIED"
        and has_text(package.get("qualification_reference"))
    )


def derived_status(knowledge_assets: object, evidence_scope: object) -> str:
    """The highest legal asset status for these assets and this evidence scope."""
    if evidence_scope == "SYNTHETIC":
        return "DRAFT_KNOWLEDGE"
    if missing_keys(knowledge_assets) or not evidence_package_qualified(knowledge_assets):
        return "DRAFT_KNOWLEDGE"
    return "CLOSED_KNOWLEDGE"


def resolved_status(claimed: object, knowledge_assets: object, evidence_scope: object) -> str:
    """Downgrade-only resolution of the caller's claim against the derived status."""
    if claimed == "CLOSED_KNOWLEDGE" and derived_status(knowledge_assets, evidence_scope) == "CLOSED_KNOWLEDGE":
        return "CLOSED_KNOWLEDGE"
    return "DRAFT_KNOWLEDGE"


def status_notes(claimed: object, knowledge_assets: object, evidence_scope: object) -> list[str]:
    """Audible NOTE lines wherever the record did not reach the caller's claim."""
    resolved = resolved_status(claimed, knowledge_assets, evidence_scope)
    if claimed != "CLOSED_KNOWLEDGE" or resolved == "CLOSED_KNOWLEDGE":
        return []
    notes: list[str] = []
    if evidence_scope == "SYNTHETIC":
        notes.append(
            "NOTE: a SYNTHETIC project can never reach CLOSED_KNOWLEDGE; the record is capped at "
            "DRAFT_KNOWLEDGE and force-marked SYNTHETIC_DEMO_ONLY (NO Synthetic Closure)"
        )
        return notes
    missing = missing_keys(knowledge_assets)
    if missing:
        notes.append(
            "NOTE: CLOSED_KNOWLEDGE requires all six assets present; missing "
            + ", ".join(missing)
            + " -> DRAFT_KNOWLEDGE"
        )
    package = asset_entries(knowledge_assets).get(QUALIFIED_ASSET_KEY)
    if not evidence_package_qualified(knowledge_assets):
        qualification = package.get("qualification") if isinstance(package, dict) else None
        notes.append(
            "NOTE: CLOSED_KNOWLEDGE requires a present evidence package whose qualification is QUALIFIED "
            f"with a qualification_reference (got {qualification!r}) -> DRAFT_KNOWLEDGE"
        )
    return notes


def cost_criterion_errors(value: object) -> list[str]:
    """Asset references that declare themselves a cost CTQ.

    Cost is a constraint, never a criterion: a cost term inside a CTQ identity means the
    project built its criteria chain around price, which is exactly the error redesign
    section 6.3 forbids. Only CTQ identities are inspected; asset references that are not
    CTQs are never matched.
    """
    references = value if isinstance(value, list) else []
    errors: list[str] = []
    for index, reference in enumerate(references):
        if not has_text(reference):
            continue
        token = reference.upper()
        if "CTQ" not in token:
            continue
        if any(term.upper() in token for term in COST_TERMS):
            errors.append(
                f"asset_reference[{index}] {reference!r} reads as a cost CTQ criterion: cost must never appear "
                "as a CTQ criterion; it belongs in the project's cost ceiling (constraint), not in the criteria chain"
            )
    return errors


def expected_decision_fields(
    knowledge_assets: object, evidence_scope: object, asset_status: object, evidence: object
) -> dict[str, str]:
    """The canonical decision block, recomputed identically by builder and validator.

    Every input is a field of the artifact itself, so the validator can rebuild the whole
    block from the frozen artifact.
    """
    present = present_keys(knowledge_assets)
    missing = missing_keys(knowledge_assets)
    closed = asset_status == "CLOSED_KNOWLEDGE"
    gap = has_gap({"evidence": evidence})
    decision = "FREEZE" if closed and not gap else "HOLD"
    if evidence_scope == "SYNTHETIC":
        scope_prefix = (
            "Synthetic test fixture / NOT_FOR_PHYSICAL_EXECUTION: this record cannot authorize stage "
            "advancement. "
        )
    else:
        scope_prefix = ""
    return {
        "decision_question": "Are the six knowledge assets complete and qualified enough to close this project's knowledge?",
        "hypothesis": (
            "A project that lands all six knowledge assets with a QUALIFIED evidence package can be archived as "
            "CLOSED_KNOWLEDGE and retrieved by later projects; anything short of that stays a draft."
        ),
        "uncertainty": (
            f"{scope_prefix}asset_status={asset_status}; {len(present)}/6 assets present. The archive records the "
            "assets the caller supplied; it does not re-verify their contents, and a DRAFT record carries no reuse "
            "guarantee beyond what its asset references state."
        ),
        "decision_rule": (
            "CLOSED_KNOWLEDGE is legal only when all six assets are present and the evidence package is present "
            "with qualification QUALIFIED and a qualification_reference; otherwise the record is capped at "
            "DRAFT_KNOWLEDGE. A SYNTHETIC project can never close. Cost never enters a CTQ criterion."
        ),
        "result": (
            f"knowledge archive recorded {len(present)}/6 assets as present"
            + (f"; missing: {', '.join(missing)}" if missing else "")
            + f"; asset_status={asset_status}."
        ),
        "decision": decision,
        "next_action": (
            "Retain the CLOSED_KNOWLEDGE archive for retrieval by later projects; it does not freeze or release "
            "the design by itself."
            if closed
            else "Retain the DRAFT_KNOWLEDGE archive and complete the missing assets or the QUALIFIED evidence "
            "package before claiming closure."
        ),
    }
