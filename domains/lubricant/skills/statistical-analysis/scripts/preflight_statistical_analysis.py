"""Reject incomplete statistical-analysis requests before a MODEL_BUILT artifact is written."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from statistical_analysis_policy import (
    VERDICT_CONSISTENT_DIFFERENCE,
    VERDICT_NO_DETECTABLE_DIFFERENCE,
    grease_route as routes_as_grease_route,
    has_gap,
    variance_blockers,
)


ROOT = Path(__file__).resolve().parents[1]
# ADDITIVE (step 12, PRECISION_GREASE_DEV): the upstream artifact types named by the plan
# (batch / screening / bench_test / variance / campaign) are appended AFTER the seven
# original entries. Nothing existing is removed or reordered, so every oil route keeps
# exactly the upstream list it had; the new entries are only ever required on the
# grease route (see UPSTREAM_GREASE and the project-type route gate below).
# TWO FIXES against the request shape deciding the validation (step 3 of the E2E chain):
#   1. the GO requirement is applied per artifact KIND (verdict vs record, RECORD_UPSTREAM),
#      because bench_test carries UNDECIDED by contract and no oil route uses it, and the
#      campaign ledger (a record of the loop's state) must not be asked for a verdict; and
#   2. the grease precondition is read from the charter's project_type, so a grease project
#      that omits the four inner-loop keys HOLDs instead of falling through to the oil path.
# E-2 (step 14 modeling entry): the grease route also supplies the CAMPAIGN ledger, and its
# EXPERIMENT_RUNNING artifact becomes OPTIONAL -- EXPERIMENT_RUNNING is on no grease route,
# so the route's measurements live in its bench records instead (see ROUTE_OBSERVED below).
SCHEMAS = ("common.schema.json", "project.schema.json", "challenge.schema.json", "failure_ctq.schema.json", "test_method.schema.json", "design_space.schema.json", "experiment_design.schema.json", "experiment.schema.json", "model.schema.json", "batch.schema.json", "screening.schema.json", "bench_test.schema.json", "variance.schema.json", "campaign.schema.json")
UPSTREAM = (("project_artifact", "project.schema.json", "PROJECT_DEFINED"), ("challenge_artifact", "challenge.schema.json", "CHALLENGES_DEFINED"), ("failure_ctq_artifact", "failure_ctq.schema.json", "FAILURE_CTQ_DEFINED"), ("test_method_artifact", "test_method.schema.json", "TEST_METHODS_QUALIFIED"), ("design_space_artifact", "design_space.schema.json", "DESIGN_SPACE_DEFINED"), ("experiment_design_artifact", "experiment_design.schema.json", "EXPERIMENT_DESIGNED"), ("experiment_artifact", "experiment.schema.json", "EXPERIMENT_RUNNING"), ("batch_artifact", "batch.schema.json", "BATCH_PRODUCED"), ("screening_artifact", "screening.schema.json", "SCREENING_PASSED"), ("bench_test_artifact", "bench_test.schema.json", "BENCH_TESTED"), ("variance_artifact", "variance.schema.json", "VARIANCE_ASSESSED"), ("campaign_artifact", "campaign.schema.json", "CAMPAIGN_OPENED"))
# Upstream entries the six oil routes use. Kept as the original seven, verbatim, so an
# oil request is validated against exactly the list it was validated against before.
UPSTREAM_OIL = UPSTREAM[:7]
# Upstream entries the precision-grease inner loop adds. Required only when the
# supplied project charter routes as PRECISION_GREASE_DEV; on any other route they are
# neither required nor read, which is what keeps the oil paths byte-for-byte unchanged.
UPSTREAM_GREASE = UPSTREAM[7:]
# Which upstream artifacts may be asked for ``decision: GO``, and which may not.
#
# ``decision: GO`` is a VERDICT requirement, so it is only meaningful for an artifact
# whose own contract derives a GO/HOLD verdict from the record it carries: for those,
# a non-GO value (HOLD) is a legitimate producer output that this gate must refuse.
# An artifact whose contract records an observation instead is exempt, because demanding
# GO from it refuses the very artifact its producer is required to write.
#
# The twelve upstream artifacts, judged by what their own producers do:
#
#   * bench_test_artifact - RECORD (exempt). Its contract fixes ``decision`` to
#     UNDECIDED: bench_test_policy.py ("The decision is UNDECIDED on purpose: a
#     single bench run is a record, and whether the round's difference is real is decided
#     at Step 12 (variance-assessment)"), written by its decision block, and the module
#     docstring says the same. Requiring GO from it
#     made MODEL_BUILT unreachable on the one route that owns bench_test.
#   * campaign_artifact - RECORD (exempt). The ledger records the inner loop's state, not
#     a verdict: step 14 runs mid-loop, and a ledger whose newest recorded round ended
#     CONTINUE stands open (its producer writes GO), while the exit-round ledger is a
#     record of the loop having closed. Demanding GO from it would make the modeling
#     entry depend on the W2 write timing (D-1/D-2) instead of on the round's records.
#   * test_method_artifact - VERDICT. qualification_policy.py:221: "GO" if qualified else "HOLD".
#   * design_space_artifact - VERDICT. design_space_policy.py:173: "GO" if ready else "HOLD".
#   * experiment_design_artifact - VERDICT. doe_design_policy.py:96 and :135: "GO" if ready else "HOLD".
#   * batch_artifact - VERDICT. grease_batch_policy.py:669: decision = "GO" if not blockers else "HOLD".
#   * screening_artifact - VERDICT. grease_screening_policy.py:446: decision = "GO" if not blockers else "HOLD".
#   * variance_artifact - VERDICT, dispatched by VERDICT (E-1 / E6=A), not by decision:
#     variance_assessment_policy.py:760-764 gives GO exactly for the releasing verdict and
#     HOLD otherwise, and a produced HOLD record is legitimate -- NO_DETECTABLE_DIFFERENCE
#     ("a capable design found nothing") is a REAL conclusion that may close into a model,
#     so this gate reads the verdict through ``variance_blockers`` and checks the decision
#     against it (see ``variance_gate_errors``); UNDERPOWERED stays blocked and is never
#     read as NO_DETECTABLE_DIFFERENCE.
#   * project_artifact, challenge_artifact, failure_ctq_artifact, experiment_artifact -
#     their producers fix the decision to GO (build_duty_challenge_artifact.py:64,
#     build_failure_ctq_artifact.py:79, preflight_experiment_import.py:134; the charter is
#     caller-assembled per project-definition/SKILL.md Step 2 and its validator accepts
#     only the contract), so a non-GO value there can only be a hand-edited artifact. All
#     four sit on the six oil routes, and keeping the requirement on them is what leaves
#     those routes' validation exactly as it was; it stays.
#
# bench_test and campaign are also the only exempt artifacts that sit on no oil route:
# contracts/state-machine.json declares BENCH_TESTED and CAMPAIGN_OPENED only under
# PRECISION_GREASE_DEV, which is why exempting them cannot move any oil path.
RECORD_UPSTREAM = frozenset({"bench_test_artifact", "campaign_artifact"})
# The one upstream key the grease route may legally omit. CHALLENGES_DEFINED is on no
# type_route, so that route records the Challenge Map link as UNROUTED:<project_id> on
# the failure record instead of producing an out-of-route artifact. Named once and used
# by the take-item loop, the key-set verdict and the project_id threshold below.
CHALLENGE_KEY = "challenge_artifact"
# E-2: EXPERIMENT_RUNNING is on no PRECISION_GREASE_DEV route either, so the grease route
# may omit the experiment path as well: the round's measurements live in its bench records
# (batch / screening / bench_test / variance), which are what step 14 models. Named once
# and used by the key-set verdict and the observed-CTQ dispatch below.
EXPERIMENT_KEY = "experiment_artifact"
INPUT_FIELDS = {key for key, _, _ in UPSTREAM} | {"analysis"}
# The grease route's own request shapes, each derived from the twelve-key union so a typo
# can never silently add a shape: the full union; the union minus the challenge path (on
# no type_route); the union minus the experiment path (E-2: EXPERIMENT_RUNNING is on no
# grease route); and the union minus both.
GREASE_NO_CHALLENGE_FIELDS = INPUT_FIELDS - {CHALLENGE_KEY}
GREASE_NO_EXPERIMENT_FIELDS = INPUT_FIELDS - {EXPERIMENT_KEY}
GREASE_NO_CHALLENGE_NO_EXPERIMENT_FIELDS = INPUT_FIELDS - {CHALLENGE_KEY, EXPERIMENT_KEY}
OIL_INPUT_FIELDS = {key for key, _, _ in UPSTREAM_OIL} | {"analysis"}
REQUEST_FIELDS = {"model_id", "requested_analyses", "response_references", "evidence"}


def schema_dir() -> Path:
    canonical = ROOT.parents[1] / "schemas"
    return canonical if all((canonical / name).is_file() for name in SCHEMAS) else ROOT / "references"


def read_path(value: object, input_path: Path) -> Path | None:
    return input_path.parent / value if isinstance(value, str) and value.strip() else None


def has_text(value: object) -> bool:
    """True for a non-empty, non-blank string (the policy module's own reading)."""
    return isinstance(value, str) and bool(value.strip())


def variance_gate_errors(artifact: dict) -> list[str]:
    """E-1 (E6=A): the variance artifact is judged by its VERDICT; the decision must match it.

    ``decision == GO`` is only the releasing verdict's own output, so it cannot be the
    admissibility rule: NO_DETECTABLE_DIFFERENCE ("a capable design found nothing") is a
    REAL conclusion that may close into a model, and its producer correctly writes HOLD.
    Admissibility is therefore read through ``variance_blockers`` (UNDERPOWERED and
    REPLICATE_INCONSISTENT stay blocked; UNDERPOWERED is never read as
    NO_DETECTABLE_DIFFERENCE), and the decision is then checked AGAINST the verdict: GO is
    legal only on CONSISTENT_DIFFERENCE, so a GO on any other verdict -- or a missing GO on
    the releasing one -- is a hand-edited artifact and is refused. The variance artifact's
    own contract is untouched: it still carries the decision ``decision_for`` derives.
    """
    verdict = artifact.get("verdict")
    blockers = variance_blockers(verdict, artifact.get("variance_id"))
    if blockers:
        return blockers
    decision = artifact.get("decision")
    if verdict == VERDICT_CONSISTENT_DIFFERENCE and decision != "GO":
        return ["variance_artifact must have decision GO"]
    if verdict == VERDICT_NO_DETECTABLE_DIFFERENCE and decision == "GO":
        return [
            "variance_artifact must not carry decision GO: NO_DETECTABLE_DIFFERENCE releases no "
            "model update (it is admissible to the model but is not a difference); only "
            "CONSISTENT_DIFFERENCE carries GO"
        ]
    return []


def campaign_binding_errors(variance: dict, campaign: dict) -> list[str]:
    """E-2: the variance record and the campaign ledger must belong to the same round.

    Entry-level on purpose: by the time step 14 runs, the campaign's counter has already
    advanced past the recorded round (W1 of the D-1 ledger: the round boundary appends the
    round's entry and points current_iteration at the NEXT round), so comparing against
    ``current_iteration`` would never match. What must match is the newest RECORDED entry
    and the variance record: the round the variance was computed for, the ledger's own
    reference to that variance, and the campaign reference the variance carries. The
    entry rule is checked only when the ledger has a recorded round; a freshly opened
    ledger records none yet, and nothing there contradicts the variance record.
    """
    errors: list[str] = []
    if variance.get("campaign_reference") != campaign.get("campaign_id"):
        errors.append("variance_artifact campaign link is invalid")
    entries = campaign.get("iterations")
    newest = entries[-1] if isinstance(entries, list) and entries and isinstance(entries[-1], dict) else None
    if newest is None:
        return errors
    if variance.get("iteration") != newest.get("iteration"):
        errors.append("variance_artifact iteration link is invalid")
    if newest.get("variance_reference") != variance.get("variance_id"):
        errors.append("variance_artifact variance link is invalid")
    return errors


def route_evidence_scope(*candidates: object) -> str | None:
    """The one evidence scope the request carries, read off whichever upstream record exists.

    On the grease route the experiment path is optional (E-2), so the scope cannot be read
    from the experiment artifact alone. Every supplied record that carries a scope must
    agree (the consistency rule above enforces it), so the first one found is the request's
    scope; when no record carries one, None reaches the schema check and HOLDs there.
    """
    for item in candidates:
        if isinstance(item, dict) and item.get("evidence_scope") in ("SYNTHETIC", "PHYSICAL"):
            return item["evidence_scope"]
    return None


def loaded_schemas() -> tuple[dict[str, dict], Registry]:
    directory = schema_dir()
    schemas = {name: json.loads((directory / name).read_text(encoding="utf-8")) for name in SCHEMAS}
    registry = Registry()
    for schema in schemas.values():
        registry = registry.with_resource(schema["$id"], Resource.from_contents(schema))
    return schemas, registry


def load_artifact(path: Path | None, schema_name: str, label: str) -> tuple[list[str], dict | None]:
    if path is None:
        return [label], None
    try:
        schemas, registry = loaded_schemas()
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return [f"{label} cannot be read: {error}"], None
    errors = [f"{label}: {error.message}" for error in Draft202012Validator(schemas[schema_name], registry=registry).iter_errors(value)]
    return errors, value if not errors else None


def request_errors(request: object, project_id: str, evidence_scope: str | None = None) -> list[str]:
    if not isinstance(request, dict) or set(request) != REQUEST_FIELDS:
        return ["analysis must contain only model_id, requested_analyses, response_references, and evidence"]
    candidate = {"schema_version": "0.1.0", "artifact_type": "model", "project_id": project_id or "input-project", "stage": "MODEL_BUILT", "evidence_scope": evidence_scope, "decision_question": "input", "hypothesis": "input", "uncertainty": "input", "decision_rule": "input", "result": "input", "decision": "GO", "next_action": "input", "experiment_reference": "input-experiment", "design_space_reference": "input-design-space", "test_method_references": ["input-method"], "engine_handoff": "PHASE4_DETERMINISTIC_ENGINE", **request}
    schemas, registry = loaded_schemas()
    return [f"analysis: {error.message}" for error in Draft202012Validator(schemas["model.schema.json"], registry=registry).iter_errors(candidate)]


def charter_project_type(data: object, input_path: Path) -> object:
    """The route marker off the request's own charter, or None when it cannot be read.

    Read before the key-set verdict because whether the challenge key may be absent at
    all is a property of the route. An unreadable or absent charter yields None, which
    ``grease_route`` reads as "not the grease route": the request then gets exactly the
    pre-change key-set verdict.
    """
    if not isinstance(data, dict):
        return None
    path = read_path(data.get("project_artifact"), input_path)
    if path is None or not path.is_file():
        return None
    try:
        project = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return project.get("project_type") if isinstance(project, dict) else None


def errors_for(data: object, input_path: Path) -> list[str]:
    if not isinstance(data, dict):
        return ["input must be a JSON object"]
    errors, artifacts = [], {}
    # The input key set is decided by the route, not by the widest list: an oil
    # request supplies exactly the seven original keys it always did, and the
    # grease route additionally supplies the five inner-loop artifacts. Requiring
    # the union on both routes would reject every oil request.
    supplied = set(data)
    charter_type = charter_project_type(data, input_path)
    charter_grease = routes_as_grease_route({"project_type": charter_type})
    # CHALLENGES_DEFINED is on no type_route, so the grease route's own shape is the
    # twelve-key union minus the challenge path; EXPERIMENT_RUNNING is on no grease route
    # either (E-2), so the union minus the experiment path (or minus both) is admitted as
    # well. Those shapes are only ever admitted when the charter is the grease route; an
    # oil request sees the original two.
    allowed_shapes = (
        (OIL_INPUT_FIELDS, INPUT_FIELDS, GREASE_NO_CHALLENGE_FIELDS,
         GREASE_NO_EXPERIMENT_FIELDS, GREASE_NO_CHALLENGE_NO_EXPERIMENT_FIELDS)
        if charter_grease
        else (OIL_INPUT_FIELDS, INPUT_FIELDS)
    )
    if supplied not in allowed_shapes:
        errors.append("input must contain only required upstream artifact paths and analysis")
    for key, schema, stage in UPSTREAM:
        if key not in supplied:
            continue
        item_errors, artifact = load_artifact(read_path(data.get(key), input_path), schema, key)
        errors.extend(item_errors)
        artifacts[key] = artifact
        if artifact and artifact.get("stage") != stage:
            errors.append(f"{key} must be stage {stage}")
        if artifact and key == "variance_artifact":
            # E-1 (E6=A): the variance artifact is judged by its VERDICT, not by
            # ``decision == GO`` -- NO_DETECTABLE_DIFFERENCE is admissible to the model
            # and its produced HOLD record must be let through (see variance_gate_errors).
            errors.extend(variance_gate_errors(artifact))
        elif artifact and key not in RECORD_UPSTREAM and artifact.get("decision") != "GO":
            errors.append(f"{key} must have decision GO")
    # The grease precondition is keyed on the supplied charter's OWN project_type, never
    # on the request's key shape: a PRECISION_GREASE_DEV project whose request omits the
    # inner-loop keys (or supplies only some of them) must HOLD, because those are
    # that route's modeling precondition. The twelve-key shape test is kept as an
    # additional trigger, so it can only ever ADD enforcement; that request is
    # validated at least as strictly as it was before.
    grease_route = supplied == INPUT_FIELDS or routes_as_grease_route(artifacts.get("project_artifact"))
    if grease_route:
        # The inner-loop artifacts are the grease route's own precondition:
        # without a variance assessment there is nothing that says whether the
        # round's difference is real, and modeling it would fit noise.
        for key, schema, stage in UPSTREAM_GREASE:
            if artifacts.get(key) is None:
                errors.append(f"{key} is required on the PRECISION_GREASE_DEV route")
    # The seven original upstream artifacts are read BY NAME, not unpacked
    # positionally: UPSTREAM grew to twelve entries for the precision-grease
    # inner loop, and a positional unpack silently becomes a crash the moment a
    # list grows (it did, and this comment is why it will not again). The five
    # additions are read by name where they are needed.
    project = artifacts.get("project_artifact")
    challenge = artifacts.get(CHALLENGE_KEY)
    failure = artifacts.get("failure_ctq_artifact")
    method = artifacts.get("test_method_artifact")
    design_space = artifacts.get("design_space_artifact")
    experiment_design = artifacts.get("experiment_design_artifact")
    experiment = artifacts.get(EXPERIMENT_KEY)
    batch = artifacts.get("batch_artifact")
    screening = artifacts.get("screening_artifact")
    bench_test = artifacts.get("bench_test_artifact")
    variance = artifacts.get("variance_artifact")
    campaign = artifacts.get("campaign_artifact")
    oil_upstream = (project, challenge, failure, method, design_space, experiment_design, experiment)
    available = [item for item in oil_upstream if item]
    scopes = {item.get("evidence_scope") for item in (method, experiment_design, experiment) if item is not None}
    if scopes - {"SYNTHETIC", "PHYSICAL"} or len(scopes) != 1:
        errors.append("test_method, experiment_design, and experiment evidence_scope values must exist and match")
    if project and project.get("status") != "ACTIVE": errors.append("project_artifact must have status ACTIVE")
    if len(available) == len(oil_upstream) and len({item.get("project_id") for item in available}) != 1: errors.append("all upstream artifact project_id values must match")
    elif grease_route and len(available) == len(oil_upstream) - 1 and len({item.get("project_id") for item in available}) != 1:
        # The grease route's single-omission shapes (no challenge path, or no experiment
        # path): the same uniformity rule, over the six upstreams that do exist.
        # Unreachable on any route that requires both, so the oil threshold above stays
        # exactly what it was.
        errors.append("all upstream artifact project_id values must match")
    if challenge and failure and failure.get("challenge_reference") != challenge.get("challenge_id"): errors.append("failure_ctq_artifact challenge link is invalid")
    if failure and method and method.get("target_failure_reference") != failure.get("failure_id"): errors.append("test_method_artifact failure link is invalid")
    if method and (method.get("qualification_status") != "QUALIFIED" or not ({"D", "P"} & set(method.get("role", [])))): errors.append("test_method_artifact must be qualified D or P")
    if design_space and method and method.get("method_id") not in (design_space.get("qualified_test_method_references") or []): errors.append("design_space_artifact method link is invalid")
    if experiment_design and design_space and experiment_design.get("design_space_reference") != design_space.get("design_space_id"): errors.append("experiment_design_artifact design-space link is invalid")
    if experiment_design and method and method.get("method_id") not in (experiment_design.get("test_method_references") or []): errors.append("experiment_design_artifact method link is invalid")
    if experiment and experiment_design and experiment.get("experiment_design_reference") != experiment_design.get("experiment_design_id"): errors.append("experiment_artifact design link is invalid")
    if experiment and design_space and experiment.get("design_space_reference") != design_space.get("design_space_id"): errors.append("experiment_artifact design-space link is invalid")
    if experiment and method and method.get("method_id") not in (experiment.get("test_method_references") or []): errors.append("experiment_artifact method link is invalid")
    # WP-07: the modeling entry stays DOE-only. Non-DOE experiment records
    # (APPLICATION_FIELD / CONFIRMATORY_NON_DOE) are legitimate imports but are
    # explicitly excluded here, naming the record and the reason. A record
    # without an explicit evidence_class is DOE_POINT by contract default.
    if experiment and experiment.get("evidence_class", "DOE_POINT") != "DOE_POINT":
        errors.append(
            f"experiment_artifact {experiment.get('experiment_id')} has evidence_class "
            f"{experiment.get('evidence_class')} and is excluded from the modeling entry; "
            "only DOE_POINT records may be modeled (non-DOE evidence never enters statistical analysis)"
        )
    # E-2: the variance record and the campaign ledger must be the same round's, judged
    # entry-level (the counter has already advanced past the recorded round at W1).
    if variance and campaign:
        errors.extend(campaign_binding_errors(variance, campaign))
    request = data.get("analysis")
    errors.extend(request_errors(request, project.get("project_id", "") if project else "", route_evidence_scope(experiment, experiment_design, method, bench_test, variance)))
    if not isinstance(request, dict): return errors
    if has_gap(request): errors.append("analysis.evidence contains GAP")
    ctqs = {item.get("ctq_id"): item for item in failure.get("ctqs", []) if isinstance(item, dict)} if failure else {}
    # E-2: the observed CTQs follow the route. An oil request reads them off the imported
    # experiment's response measurements; the grease route reads the CTQ each of its bench
    # runs recorded, because EXPERIMENT_RUNNING is on no grease route -- the round's
    # measurements live in its batch / screening / bench_test / variance records.
    if grease_route:
        observed = {bench_test.get("ctq_reference")} if isinstance(bench_test, dict) and has_text(bench_test.get("ctq_reference")) else set()
    else:
        observed = {response.get("ctq_reference") for run in experiment.get("runs", []) for response in run.get("response_measurements", []) if isinstance(response, dict)} if experiment else set()
    for response in request.get("response_references", []):
        if not isinstance(response, dict): continue
        ctq_id = response.get("ctq_reference")
        if ctq_id not in ctqs or not design_space or ctq_id not in design_space.get("ctq_references", []) or ctq_id not in observed: errors.append(f"analysis response {ctq_id} is not a linked observed CTQ")
        if not method or response.get("test_method_reference") != method.get("method_id") or method.get("method_id") not in ctqs.get(ctq_id, {}).get("test_references", []): errors.append("analysis response must link the qualified method")
    return errors


# Provenance of the recorded gap: the route contract is what says the stage is on no
# type_route, so it is what the recorded evidence cites.
ROUTE_CONTRACT_SOURCE = "contracts/state-machine.json"


def unrouted_statement(project_id: object) -> str:
    """The recorded-gap sentence. The preflight prints it, the artifact's evidence carries it."""
    return (
        "challenge_artifact not supplied on the PRECISION_GREASE_DEV route "
        f"(CHALLENGES_DEFINED is on no type_route); the Challenge Map link is recorded as "
        f"UNROUTED:{project_id}"
    )


def challenge_note(project_id: object) -> str:
    """The one audible line a grease run without a challenge artifact prints."""
    return "NOTE: " + unrouted_statement(project_id)


def unrouted_evidence(project_id: object) -> dict:
    """The ASSUMED evidence item that records the missing challenge as a route property.

    Never GAP: several preflights refuse a GAP-status item outright, and this is not an
    unresolved gap in the record - it is a recorded property of the route.
    """
    return {
        "evidence_id": f"EV-UNROUTED-{project_id}",
        "statement": unrouted_statement(project_id),
        "source": ROUTE_CONTRACT_SOURCE,
        "status": "ASSUMED",
    }


def grease_without_challenge(data: object, project: object) -> bool:
    """True for the grease route's legal no-challenge shape, and nothing else.

    Strictly gated: a non-grease charter, or a grease request that did supply a challenge
    artifact, returns False and every caller keeps the output it had. The name deliberately
    matches the module-level reading; ``errors_for`` keeps its own local flag of the same
    name, which shadows this function inside that one scope and changes nothing.
    """
    return (
        isinstance(data, dict)
        and CHALLENGE_KEY not in data
        and routes_as_grease_route(project)
    )


def route_notes(data: object, input_path: Path) -> list[str]:
    """The audible NOTE for the grease route's recorded CHALLENGES_DEFINED gap.

    Empty on every other shape: an oil request, and a grease request that supplied a
    challenge artifact, print exactly what they printed before.
    """
    if not isinstance(data, dict) or CHALLENGE_KEY in data:
        return []
    if not routes_as_grease_route({"project_type": charter_project_type(data, input_path)}):
        return []
    project_path = read_path(data.get("project_artifact"), input_path)
    project_id = None
    if project_path is not None and project_path.is_file():
        try:
            project_id = json.loads(project_path.read_text(encoding="utf-8")).get("project_id")
        except (OSError, json.JSONDecodeError, AttributeError):
            project_id = None
    return [challenge_note(project_id)]


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python preflight_statistical_analysis.py <input.json>"); return 1
    path = Path(sys.argv[1]).resolve()
    try: data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        print(f"HOLD: cannot read input: {error}; no artifact generated"); return 1
    errors = errors_for(data, path)
    if errors:
        print(f"HOLD: missing or invalid: {', '.join(errors)}; no artifact generated"); return 1
    print("READY: input can form one MODEL_BUILT request only")
    for line in route_notes(data, path): print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
