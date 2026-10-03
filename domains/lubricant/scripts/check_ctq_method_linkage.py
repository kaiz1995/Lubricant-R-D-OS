#!/usr/bin/env python3
"""check_ctq_method_linkage.py -- CTQ <-> method bare-id linkage guard.

Migrated from the validated session guard (OpenScience session
2026-10-02-1949/work/check_ctq_method_linkage.py) with the session-specific
path and generator assumptions removed.

Why this exists
---------------
``doe-design/scripts/preflight_doe_design.py`` (the design-space linkage block)
requires, for every CTQ listed in a design space, that the supplied method id
appear in that CTQ's ``test_references`` or in the failure's ``test_chain``.
A prose mention like "the corresponding method record: HDG-TM-012" does NOT
satisfy it -- the check is an exact string match. A CTQ that lost its bare
method id therefore silently poisons any future DOE built on it, while every
single artifact still passes its own schema.

Two check directions:

* **Direction A (always on, workspace-intrinsic).** Replicates the preflight
  rule across the whole workspace: for every design space, each CTQ reference
  must exist in a failure artifact and carry the design space's qualified
  method id in ``test_references`` (or the failure's ``test_chain``). Also
  flags dangling method ids referenced from failure CTQs.
* **Direction B (opt-in).** The original session check: every method's
  *declared* CTQs (read from a generator-style source file via
  ``--declared-map <file>``) must appear as a record whose ``test_references``
  / ``test_chain`` carry that bare method id. Methods that deliberately own no
  CTQ are passed via repeatable ``--exception <method_id>``.

Usage::

    python check_ctq_method_linkage.py <workspace_dir>
    python check_ctq_method_linkage.py <workspace_dir> --declared-map gen_test_methods.py \
        [--exception HDG-TM-008] ...

Exit 0 if the invariant holds; exit 1 with violations otherwise. Pure stdlib.
"""

import argparse
import json
import re
import sys
from pathlib import Path

# Direction B: pull "method_id": "...", "ctq": "..." pairs out of a generator
# source file, same extraction the session guard used.
DECLARED_RE = re.compile(r'"method_id":\s*"([A-Za-z0-9\-]+)".*?"ctq":\s*"([^"]+)"', re.S)
CTQ_ID_RE = re.compile(r"[A-Z0-9]+-CTQ-\d+-[A-Z]")
# test_references entries are not required to be method ids (standards citations
# such as "ISO 3744:2025 (...)" are legal content); but an entry that *looks
# like* a bare method id must resolve to a test_method artifact.
METHOD_ID_FULL_RE = re.compile(r"[A-Z0-9]+(?:-[A-Z0-9]+)*-TM-\d+")


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def collect_ctqs(workspace):
    """ctq_id -> {failure, refs, chain, file} from all failure_ctq artifacts."""
    ctqs = {}
    for path in sorted(workspace.glob("failure_ctq*.json")):
        try:
            fa = load_json(path)
        except (OSError, ValueError) as exc:
            print(f"WARN cannot parse {path.name}: {exc}")
            continue
        if not isinstance(fa, dict):
            continue
        for c in fa.get("ctqs", []) or []:
            if isinstance(c, dict) and c.get("ctq_id"):
                ctqs[c["ctq_id"]] = {
                    "failure": fa.get("failure_id"),
                    "refs": list(c.get("test_references") or []),
                    "chain": list(fa.get("test_chain") or []),
                    "file": path.name,
                }
    return ctqs


def collect_methods(workspace):
    """method_id -> qualification_status from all test_method artifacts."""
    methods = {}
    for path in sorted(workspace.glob("test_method*.json")):
        try:
            a = load_json(path)
        except (OSError, ValueError) as exc:
            print(f"WARN cannot parse {path.name}: {exc}")
            continue
        if isinstance(a, dict) and a.get("method_id"):
            methods[a["method_id"]] = a.get("qualification_status")
    return methods


def collect_design_spaces(workspace):
    paths = sorted(workspace.glob("design_space*.json"))
    out = []
    for path in paths:
        try:
            a = load_json(path)
        except (OSError, ValueError) as exc:
            print(f"WARN cannot parse {path.name}: {exc}")
            continue
        if isinstance(a, dict):
            out.append((path.name, a))
    return out


def direction_a(workspace, ctqs, methods):
    """The preflight-replicated rule, workspace-wide."""
    violations = []

    # Dangling bare method ids referenced from failure CTQs (standards-citation
    # entries are not method ids and are ignored).
    for cid, rec in sorted(ctqs.items()):
        for mid in rec["refs"]:
            if METHOD_ID_FULL_RE.fullmatch(mid) and mid not in methods:
                violations.append(
                    f"{cid} ({rec['failure']}): test_references points at unknown method {mid}"
                )

    # Every design space: method exists & QUALIFIED, CTQs exist & linked bare-id.
    for name, ds in collect_design_spaces(workspace):
        mids = ds.get("qualified_test_method_references") or []
        for mid in mids:
            if mid not in methods:
                violations.append(f"{name}: qualified method {mid} does not exist")
            elif methods[mid] != "QUALIFIED":
                violations.append(f"{name}: qualified method {mid} is {methods[mid]!r}")
        for cid in ds.get("ctq_references", []) or []:
            rec = ctqs.get(cid)
            if rec is None:
                violations.append(f"{name}: ctq_reference {cid} does not exist in any failure_ctq")
                continue
            for mid in mids:
                if mid not in rec["refs"] and mid not in rec["chain"]:
                    violations.append(
                        f"{name}: {cid} ({rec['failure']}) is not linked to {mid} "
                        f"-> preflight would reject a DOE here"
                    )
    return violations


def declared_map(path):
    """method_id -> sorted CTQ ids it declares (negation clauses dropped)."""
    text = Path(path).read_text(encoding="utf-8")
    out = {}
    for mid, ctq in DECLARED_RE.findall(text):
        ids = CTQ_ID_RE.findall(ctq)
        # drop the ids that appear only inside a negation clause
        out[mid] = sorted({i for i in ids if i in ctq.split("不再承担")[0]})
    return out


def direction_b(declared, exceptions, ctqs, methods):
    """The original session rule: every declared CTQ carries the bare method id."""
    violations = []
    for mid, cids in sorted(declared.items()):
        if mid in exceptions or not cids:
            continue
        for cid in cids:
            rec = ctqs.get(cid)
            if rec is None:
                violations.append(f"{cid}: declared by {mid} but does not exist")
                continue
            if mid in rec["refs"] or mid in rec["chain"]:
                continue
            violations.append(
                f"{cid} ({rec['failure']}): declares {mid} "
                f"[{methods.get(mid, '?')}] but the bare id is absent from "
                f"test_references/test_chain -> preflight would reject a DOE here"
            )
    return violations


def main(argv):
    parser = argparse.ArgumentParser(description="CTQ <-> method bare-id linkage guard")
    parser.add_argument("workspace_dir")
    parser.add_argument("--declared-map", default=None,
                        help="generator-style source file declaring method->CTQ (enables direction B)")
    parser.add_argument("--exception", action="append", default=[],
                        help="method id that deliberately owns no CTQ (repeatable)")
    args = parser.parse_args(argv[1:])

    workspace = Path(args.workspace_dir)
    if not workspace.is_dir():
        print(f"FAIL: workspace_dir '{workspace}' is not a directory")
        return 2

    ctqs = collect_ctqs(workspace)
    methods = collect_methods(workspace)

    violations = direction_a(workspace, ctqs, methods)

    if args.declared_map:
        declared = declared_map(args.declared_map)
        violations.extend(direction_b(declared, set(args.exception), ctqs, methods))
        claimed = {c for cs in declared.values() for c in cs}
        orphans = [cid for cid in ctqs if cid not in claimed]
    else:
        orphans = []

    print(f"CTQs found: {len(ctqs)}   methods found: {len(methods)}")
    if args.declared_map:
        print(
            f"declared map: {args.declared_map}   documented exceptions (no own CTQ): "
            f"{', '.join(sorted(args.exception)) or '(none)'}"
        )
        if orphans:
            print("CTQs claimed by no method (auxiliary or orphan - review):")
            for o in orphans:
                print(f"  {o}  <- {ctqs[o]['failure']}")
    print()
    if violations:
        print("VIOLATIONS:")
        for v in violations:
            print(f"  {v}")
        return 1
    print("invariant holds: every design-space CTQ carries the bare qualified method id")
    if args.declared_map:
        print("invariant holds: every declared CTQ carries the bare method id")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
