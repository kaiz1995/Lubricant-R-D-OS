# Upstream Baseline

```yaml
upstream_repository: https://github.com/ai4s-research/open-science.git
upstream_branch: master
upstream_version: 0.5.2
upstream_commit: cea3c3a504285810243e8bb54b9d5c41496a84eb
latest_fetched_upstream_commit: cea3c3a504285810243e8bb54b9d5c41496a84eb
baseline_ahead: 0
baseline_behind: 0
last_sync: 2026-09-14
sync_status: SYNCED

downstream_repository: https://github.com/kaiz1995/Lubricant-R-D-OS.git
downstream_branch: dev/lubricant-rd-v0
downstream_working_branch: feat/lubricant-rd-ui-minimal
# Both branches point at the same commit as of 2026-09-22; dev/ is the
# integration line named in §2 of the sync spec, feat/ is where the UI work
# landed first.

local_product:
  name: Lubricant R&D OS
  version: 0.1.0-dev

domain_layer:
  # Merged into this repository on 2026-09-22 (merge commit d7e064f), per §20 of
  # 03_Open_science二次开发与上游同步规范, which places the domain layer at
  # domains/lubricant/ rather than in a separate repository.
  location: domains/lubricant/
  merged_commit: d7e064ff0e2edf44487525183eead753f4fa5116
  history_commits: 92          # reachable via the merge's second parent
  previous_repository: https://github.com/kaiz1995/lubricant-rd-domain-pack.git

core_modifications:
  # Review with: git log upstream/master..HEAD -- apps packages crates
  # New files (no upstream counterpart):
  - apps/desktop/src/lib/lubricantContracts.ts
  - apps/desktop/src/lib/lubricantArtifacts.ts
  - apps/desktop/src/lib/lubricantGate.ts
  - apps/desktop/src/components/lubricant/LubricantStagePane.tsx
  - apps/desktop/src/app/routes/LubricantWorkbenchPage.tsx
  # Edits to upstream files (keep small and concentrated):
  - apps/desktop/src/app/router.tsx                    # /lubricant route
  - apps/desktop/src/components/session/SessionView.tsx # right-pane mount + toolbar toggle
  - apps/desktop/src/components/sidebar/Sidebar.tsx     # nav entry
  - apps/desktop/src/i18n/locales/*/{nav,session}.json  # 7 locales
  - apps/desktop/src-tauri/Cargo.toml                   # drop macos-private-api feature

compatibility_status:
  upstream_compat_tests: PASS
  lubricant_stage_chain: PASS_THROUGH_DESIGN_SPACE
  lubricant_full_e2e: PASS
  desktop_three_pane: VERIFIED_ON_WINDOWS

notes:
  - The domain layer is 359 files that do not exist upstream, so
    `git merge upstream/master` cannot conflict on them. Filtering by path is
    what keeps the core-modification list readable.
  - tauri.macos.conf.json still declares `macOSPrivateApi: true` while
    Cargo.toml no longer enables the `macos-private-api` feature. Windows is
    unaffected; a macOS build needs one of the two sides changed.
  - The stage-chain smoke uses canonical validated artifacts where Stage 0-2
    builders do not yet exist.
  - DOE, experiment import, statistical analysis, Gate, and Freeze remain
    outside the accepted baseline.
```
