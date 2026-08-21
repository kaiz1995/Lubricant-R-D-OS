# Upstream Baseline

```yaml
upstream_repository: https://github.com/ai4s-research/open-science.git
upstream_branch: master
upstream_version: 0.5.0
upstream_commit: a3a1a02e9a0bfc258f6f2671c22f823374c38173
latest_fetched_upstream_commit: b51714d007834053c7d0c0dbd1794478ebde931e
baseline_ahead: 0
baseline_behind: 2
last_sync: 2026-08-20
sync_status: UPDATE_AVAILABLE

downstream_repository: https://github.com/kaiz1995/Lubricant-R-D-OS.git
downstream_branch: dev/lubricant-rd-v0

local_product:
  name: Lubricant R&D OS
  version: 0.1.0-dev

domain_layer:
  external_repository: lubricant-rd-domain-pack
  stable_commit: 3d935cd64422dc50c56c2efef52e47d83d204fec
  pending_wip_branch: wip/doe-design-freeze
  pending_wip_commit: 862f33a2c6fea36f5ef192cbec8f497b71779c2c

core_modifications: []

compatibility_status:
  upstream_compat_tests: PASS
  lubricant_stage_chain: PASS_THROUGH_DESIGN_SPACE
  lubricant_full_e2e: BLOCKED_NOT_IMPLEMENTED

notes:
  - origin is currently an empty repository and this baseline has not been pushed.
  - The Domain layer is maintained independently from the upstream Core repository.
  - This metadata extension is not a Core patch.
  - The stage-chain smoke uses canonical validated artifacts where Stage 0-2 builders do not yet exist.
  - DOE, experiment import, statistical analysis, Gate, and Freeze remain outside the accepted baseline.
```
