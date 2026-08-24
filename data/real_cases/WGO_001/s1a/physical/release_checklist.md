# WGO_001 S1a Physical Run Release Checklist

Overall status: `DRAFT_NOT_RELEASED`

Authoring: `PASS/FREEZE`

Execution Package Draft Gate: `PASS/FREEZE`

Physical Run Release: `HOLD`

| # | Release condition | Status | Evidence / gate |
|---|---|---|---|
| 1 | `GOOD_CHARACTERIZATION_CANDIDATE` identity frozen | HOLD | Synthetic demo identity confirmed; not physical-release evidence. |
| 2 | `BAD_CHARACTERIZATION_CANDIDATE` identity frozen | HOLD | Synthetic assumption confirmed; not physical-release evidence. |
| 3 | `BENCH_REFERENCE_BLANK` identity frozen | HOLD | Synthetic demo container identity confirmed; not physical-release evidence. |
| 4 | `STOP_REASON_V1` frozen | MET | Seven canonical values frozen for new physical runs; legacy values preserved separately. |
| 5 | Q2-B checkpoints owner-approved | HOLD | 1 h/2 h frozen for synthetic demo only. |
| 6 | Protocol version frozen | HOLD | Candidate protocol exists; released version not signed. |
| 7 | 65 dB event endpoint frozen | HOLD | `FIRST_REACH_65_DB` drafted; owner confirmation pending. |
| 8 | 10 h censoring semantics frozen | HOLD | Administrative right-censor semantics drafted; owner confirmation pending. |
| 9 | Operator/equipment record fields ready | MET | Template includes operator, equipment, bench and environment fields. |
| 10 | Owner physical-run release sign-off complete | HOLD | No release signature recorded. |
| 11 | Blocking conditions and execution order frozen | HOLD | Balanced order frozen for synthetic demo only; physical order not released. |
| 12 | Event-detection rule frozen | HOLD | Rule frozen for synthetic demo only; no physical method qualification. |
| 13 | Release manifest generated and hashes verified | HOLD | Draft manifest exists only; artifact hashes remain null until the release set is frozen. |

Release readiness: `ENTERED`. Owner must freeze all required parameters before a formal execution order is generated.

Release decision: `HOLD`. No condition above authorizes a physical run. All 13 conditions must be simultaneously `PASS` plus Owner authorization before `RELEASED_FOR_EXECUTION` is permitted. `AGENT_WAIVER`, `PARTIAL_RELEASE`, and `SILENT_EXCEPTION` are prohibited. A deviation is valid only as an Owner-approved `RELEASE_DEVIATION`; it does not add a 14th condition. A2 remains `RESERVED_NOT_RELEASED`; it becomes eligible only after A1 is `PROMISING` and the owner approves it.
