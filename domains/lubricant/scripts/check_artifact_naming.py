#!/usr/bin/env python3
"""check_artifact_naming.py -- Lubricant domain pack artifact naming checker.

This script encodes two contracts of the Lubricant R&D domain pack:

1. **Canonical-name contract**: the OS workbench stage-gate panel ("研发阶段与门禁")
   decides whether a stage is complete by looking up the *canonical* artifact name
   (e.g. ``challenge.json``) with an EXACT match. The canonical name of each stage
   type is ``<type>.json``; additional records of the same stage must be appended
   as ``<type>-<project_id>-<id>.json`` suffixed names (also legal). Any mangled
   variant (wrong separator such as ``_`` or ``--``, misspelled type name, ...)
   is invisible to the panel and is reported here as a violation.

2. **``project.json.stage`` constant invariant**: the ``stage`` field of
   ``project.json`` is the constant marker ``"PROJECT_DEFINED"``. It is NOT a
   "current progress" field to be advanced. Seven preflight scripts in this
   domain pack hard-require ``stage == "PROJECT_DEFINED"`` (duty-definition,
   failure-ctq-analysis, doe-design, formulation-design, experiment-import,
   gate-review, optimization). If it has been advanced to any other value the
   workspace is broken and this script reports a violation.

Usage::

    python check_artifact_naming.py <workspace_dir>

Output: one conclusion per line; per-type statistics are printed. If any
violation exists the last line starts with ``HOLD:`` and exit code is 1;
otherwise the last line starts with ``PASS:`` and exit code is 0.

Pure standard library. No third-party dependencies.
"""

import json
import os
import sys

# The 13 stage types tracked by the stage-gate panel (canonical names:
# <type>.json). Order here is display order; suffix matching uses longest-prefix.
STAGE_TYPES = [
    "project",
    "duty",
    "challenge",
    "failure_ctq",
    "test_method",
    "design_space",
    "experiment_design",
    "experiment",
    "model",
    "optimization",
    "process",
    "gate",
    "application",
]

# Longest-first so that ``experiment_design-*.json`` is never misattributed
# to the shorter prefix ``experiment-``.
STAGE_TYPES_BY_LENGTH = sorted(STAGE_TYPES, key=len, reverse=True)

PROJECT_STAGE_CONSTANT = "PROJECT_DEFINED"


def _normalize(stem):
    """Collapse separators so mangled names still resemble their type."""
    return stem.replace("-", "").replace("_", "")


def classify(filename):
    """Classify one root-level ``*.json`` filename.

    Returns ``(status, type_or_None)`` where status is one of
    ``"canonical"`` (exactly ``<type>.json``), ``"suffixed"`` (legal
    ``<type>-<...>.json``), ``"violation"`` (mangled/misspelled stage
    artifact), or ``"unrelated"`` (not a stage artifact; ignored).
    """
    stem = filename[: -len(".json")]
    if stem in STAGE_TYPES:
        return "canonical", stem
    for t in STAGE_TYPES_BY_LENGTH:
        if stem.startswith(t + "-"):
            return "suffixed", t
    norm = _normalize(stem)
    for t in STAGE_TYPES_BY_LENGTH:
        nt = _normalize(t)
        if norm.startswith(nt) and len(norm) > len(nt):
            return "violation", t
    return "unrelated", None


def check_workspace(workspace_dir):
    """Run all checks. Returns (lines, violations) before the verdict line."""
    lines = []
    violations = []

    stats = {t: {"canonical": False, "records": 0} for t in STAGE_TYPES}

    entries = sorted(
        f
        for f in os.listdir(workspace_dir)
        if f.endswith(".json") and os.path.isfile(os.path.join(workspace_dir, f))
    )

    for filename in entries:
        status, stage_type = classify(filename)
        if status == "canonical":
            stats[stage_type]["canonical"] = True
            stats[stage_type]["records"] += 1
        elif status == "suffixed":
            stats[stage_type]["records"] += 1
        elif status == "violation":
            violations.append(
                "{}: mangled stage artifact resembling '{}' (wrong separator or "
                "misspelled type); legal names are '{}.json' or "
                "'{}-<project_id>-<id>.json'".format(
                    filename, stage_type, stage_type, stage_type
                )
            )
        # "unrelated" json files are not stage artifacts: ignored.

    for t in STAGE_TYPES:
        lines.append(
            "{}: canonical={}, records={}".format(
                t, "yes" if stats[t]["canonical"] else "no", stats[t]["records"]
            )
        )

    # project.json existence / parseability / stage-constant invariant.
    project_path = os.path.join(workspace_dir, "project.json")
    if not os.path.isfile(project_path):
        violations.append(
            "project.json: missing. This file is mandatory: 7 preflight scripts "
            "(duty-definition, failure-ctq-analysis, doe-design, "
            "formulation-design, experiment-import, gate-review, optimization) "
            "hard-require it with stage == \"{}\".".format(PROJECT_STAGE_CONSTANT)
        )
    else:
        try:
            with open(project_path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError) as exc:
            violations.append(
                "project.json: cannot be parsed as JSON ({}).".format(exc)
            )
        else:
            stage = data.get("stage") if isinstance(data, dict) else None
            if stage != PROJECT_STAGE_CONSTANT:
                violations.append(
                    "project.json: stage is {!r} but must be the constant "
                    "\"{}\". NOTE: this field is a fixed marker required by 7 "
                    "preflight scripts, NOT a 'current project stage' to be "
                    "advanced; it must never be moved to another value.".format(
                        stage, PROJECT_STAGE_CONSTANT
                    )
                )

    return lines, violations


def main(argv):
    if len(argv) != 2:
        print("Usage: python check_artifact_naming.py <workspace_dir>")
        return 2
    workspace_dir = argv[1]
    if not os.path.isdir(workspace_dir):
        print("HOLD: workspace_dir '{}' is not a directory".format(workspace_dir))
        return 2

    stat_lines, violations = check_workspace(workspace_dir)
    for line in stat_lines:
        print(line)
    for v in violations:
        print("VIOLATION: {}".format(v))

    if violations:
        print(
            "HOLD: {} violation(s): {}".format(len(violations), " | ".join(violations))
        )
        return 1
    print("PASS: artifact naming conforms to the canonical-name contract")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
