from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from domains.lubricant.compute.validation.common import canonical_digest
from domains.lubricant.compute.validation.engine import validate_request

FIXTURES = ROOT / "fixtures" / "compute"


def load(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def request(kind, data, context=()):
    return {"input_type": "VALIDATION_REQUEST", "artifact": {"artifact_type": kind + "_result", "data": data}, "chain_context": list(context)}


def context(kind, data, digest=None):
    return {"artifact_type": kind + "_result", "digest": digest or canonical_digest(data), "data": data}


def status(req):
    return validate_request(req)["result"]


def rejected(req):
    envelope = validate_request(req)
    assert envelope["status"] == "REJECTED"
    assert len(envelope["rejection_reasons"]) > 0
    assert envelope["result"]["overall_status"] == "REJECTED"
    return envelope["result"]


def add_bounds(doe):
    ids = set(doe["result"]["runs"][0]["proportions"])
    doe["parameters"]["design_space_bounds"] = {key: {"lower": 0.0, "upper": 1.0} for key in ids}
    return doe


def compatible_doe(statistics):
    doe = load("doe-gold-output.json")
    ids = sorted({part[2:] for term in statistics["parameters"]["term_order"] for part in term.split("*")})
    for run in doe["result"]["runs"]:
        values = list(run["proportions"].values())
        run["proportions"] = {ids[0]: values[0], ids[1]: values[1], ids[2]: sum(values[2:])}
    return add_bounds(doe)


def valid_optimization():
    optimization = load("optimization-gold-output.json")
    optimization["result"]["method_summary"]["effective_domain_note"] = "BOUNDING_BOX_APPROX_V1: A=[0,1], B=[0,1], C=[0,1]"
    statistics = load("statistics-gold-output.json")
    cost = load("cost-gold-output.json")
    return optimization, statistics, cost


def main():
    # 1 valid cost
    cost = load("cost-gold-output.json")
    assert status(request("cost", cost))["overall_status"] == "VALID"
    # 2 cost contribution sum anomaly
    bad = copy.deepcopy(cost); bad["result"]["components"][0]["cost_percentage"] += 1
    rejected(request("cost", bad))
    # 3 valid DOE
    doe = add_bounds(load("doe-gold-output.json"))
    assert status(request("doe", doe))["overall_status"] == "VALID"
    # 4 DOE proportion/bounds broken
    bad = copy.deepcopy(doe); bad["parameters"]["design_space_bounds"]["AN"]["lower"] = 0.1
    rejected(request("doe", bad))
    no_evidence = load("doe-gold-output.json")
    result = rejected(request("doe", no_evidence))
    assert any(x["check_id"] == "doe.bounds_evidence" and x["severity"] == "FATAL" for x in result["checks"])
    # 5 valid Statistics with DOE context
    statistics = load("statistics-gold-output.json"); stats_doe = compatible_doe(statistics)
    assert status(request("statistics", statistics, [context("doe", stats_doe)]))["overall_status"] == "VALID"
    # 6 Statistics term/component mismatch
    bad = copy.deepcopy(statistics); bad["result"]["coefficients"][0]["term"] = "x_MISSING"
    rejected(request("statistics", bad, [context("doe", stats_doe)]))
    # 7 DOMAIN_SCREENED_APPROX warning
    optimization, opt_stats, opt_cost = valid_optimization()
    warned = copy.deepcopy(optimization); warned["result"]["method_summary"]["effective_domain_note"] += "; DOMAIN_SCREENED_APPROX"
    assert status(request("optimization", warned, [context("statistics", opt_stats), context("cost", opt_cost)]))["overall_status"] == "VALID_WITH_WARNINGS"
    # 8 valid Optimization
    assert status(request("optimization", optimization, [context("statistics", opt_stats), context("cost", opt_cost)]))["overall_status"] == "VALID"
    # 9 guardrail FAIL candidate
    bad = copy.deepcopy(optimization); bad["result"]["recommended_candidates"][0]["margin_report"][0]["passes"] = False
    rejected(request("optimization", bad, [context("statistics", opt_stats), context("cost", opt_cost)]))
    # 10 Statistics missing DOE
    result = rejected(request("statistics", statistics)); assert any(x["severity"] == "FATAL" for x in result["checks"])
    # 11 Optimization missing required dependencies
    result = rejected(request("optimization", optimization)); assert sum(x["severity"] == "FATAL" for x in result["checks"]) == 2
    # 12 DOE -> Statistics mismatch
    result = rejected(request("statistics", statistics, [context("doe", doe)])); assert result["upstream_consistency"]["doe_to_statistics"] == "MISMATCH"
    # 13 Statistics model digest mismatch
    bad = copy.deepcopy(optimization); bad["parameters"]["source_statistics_digest"] = "0" * 64
    rejected(request("optimization", bad, [context("statistics", opt_stats), context("cost", opt_cost)]))
    # 14 declared context digest mismatch
    result = rejected(request("statistics", statistics, [context("doe", stats_doe, "0" * 64)])); assert any(x["severity"] == "FATAL" for x in result["checks"])
    # Context artifact_type must identify its embedded engine.
    mismatched_context = context("cost", opt_stats)
    result = rejected(request("optimization", optimization, [context("statistics", opt_stats), mismatched_context]))
    assert any(x["check_id"] == "provenance.type_engine.cost_result" and x["severity"] == "ERROR" for x in result["checks"])
    # 15 unknown engine/version
    bad = copy.deepcopy(cost); bad["engine_name"] = "unknown"
    rejected(request("cost", bad))
    bad = copy.deepcopy(cost); bad["engine_version"] = "9.9.9"
    rejected(request("cost", bad))
    # 16 artifact type/engine mismatch
    rejected(request("doe", cost))
    # 17 deterministic CLI double run byte-identical
    with tempfile.TemporaryDirectory() as td:
        a = Path(td) / "a.json"; b = Path(td) / "b.json"; inp = FIXTURES / "validation-gold-input.json"
        command = [sys.executable, "-m", "domains.lubricant.compute.validation.engine", str(inp)]
        subprocess.run(command + [str(a)], cwd=ROOT, check=True); subprocess.run(command + [str(b)], cwd=ROOT, check=True)
        assert a.read_bytes() == b.read_bytes()
    # 18 gold fixture SHA256 freeze and exact regeneration
    gold_input = (FIXTURES / "validation-gold-input.json").read_bytes()
    gold_output = (FIXTURES / "validation-gold-output.json").read_bytes()
    assert hashlib.sha256(gold_input).hexdigest() == "2b83d2eb90aec794d5334a6dec7e7abd2520f6c03c14fa0af73cf55bb5cb9d62"
    assert hashlib.sha256(gold_output).hexdigest() == "61ada1a3c8be2bda81042da5e8f2b7a70373ab87e45432660cb719111543dc3a"
    assert gold_output == (json.dumps(validate_request(json.loads(gold_input.decode("utf-8")), gold_input), ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    print("validation engine tests passed (18 scenarios)")


if __name__ == "__main__":
    main()
