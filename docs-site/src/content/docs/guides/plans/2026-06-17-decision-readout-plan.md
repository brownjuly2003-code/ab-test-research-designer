---
title: "Plan — Decision Readout (ship/no-ship synthesis)"
---

# Plan — Decision Readout (ship/no-ship synthesis)

**Author:** Claude Opus 4.8 (1M context)
**Date:** 2026-06-17
**Status:** proposed (not started)
**Type:** product-value vertical slice (forward-looking, not tech-debt)

## Context / state at authoring
- Local `main = bdf430e8`; live HF Space commit `6ec74a25` (`assets/index-D2Juengw.js`); GitHub origin **not** pushed (deploy is HF `upload_folder`, not git push).
- Branch `fix/ux-audit-i18n-polish` merged into local main.
- §5.4 product features + execution-MVP (Phases A→D, ext E1–E5) are **closed**. This plan is the next product layer.
- Just landed (2026-06-17): post-test verdict/interpretation localization (backend i18n + frontend `Accept-Language`), es/de mojibake repair (121 strings), fr/zh/ar observed-results term fixes, MDE/uplift hint, float formatting, wizard footer regrouping, CSP theme-init externalization. All deployed + verified live.

## Idea
Every live-experiment signal already exists **separately** (frequentist effect+CI, Bayesian P(B>A), SRM, sequential crossing, CUPED-adjusted, guardrails). The user still assembles the decision by hand. **Flagship: one synthesized verdict — ship / don't ship / keep running — plus an exportable readout.** This is the actual job-to-be-done and on-brand with the "decision-ready reports, all from one backend run" positioning.

---

## P0 — Foundation: locale content gate (~45 min, BEFORE features)
Cheap insurance against the bug class the 2026-06-17 audit exposed (mojibake sat unnoticed in es/de for months because CI checked key parity, not content).
- Validator over `app/frontend/public/locales/*.json` AND `app/backend/app/i18n/*.json`: fail on `[A-Za-zÀ-ÿ]\?[A-Za-zÀ-ÿ]` (mojibake) and U+FFFD; whitelist genuine question marks (`¿…?`, trailing `…?`).
- Wire into `scripts/verify_all.py` + a dedicated CI step next to the key-parity check.
- **Verify:** green on current locales; fails on an injected `Franc?s`.

## P1 — Flagship "Decision Readout" (vertical slice, ~2–3h)
Follow the project cycle: branch → slice → i18n ×7 → tests → gate → deploy.
1. **Backend** `services/decision_service.py`: `synthesize_decision(live_stats) -> {verdict: ship|no_ship|keep_running, confidence, reasons[], blockers[]}`. **No new math** — rules over existing `live_stats` fields:
   - SRM mismatch → blocker; guardrail breach → blocker.
   - sequential crossing up + P(B>A) ≥ threshold → ship.
   - CI crosses 0 and info-fraction < 1 → keep_running.
   - thresholds = configurable constants (constants.py).
2. **Endpoint** `GET /api/v1/experiments/{id}/decision` (read auth), reuses live-stats aggregates.
3. **Frontend** `components/results/DecisionReadoutSection.tsx` — traffic-light verdict + reasons/blockers + hook into existing markdown/html export. Direct `t` from `../i18n`, no new charts.
4. **i18n** namespace `results.decision` ×7 (clean thanks to P0 gate). If the verdict text is backend-emitted (like `results.verdict` today), add to backend catalogs too — `Accept-Language` already wired.
5. **Tests:** rule/property coverage (each blocker/verdict branch), route happy+404, vitest render of 3 states.
- **Verify:** `verify_all.py --skip-smoke` serial green; CI ubuntu-e2e + verify-postgres; live check on `?admin=1` in EN + RU.

## P2 — Stretch (if budget remains, one at a time)
- **Segment breakdown** of live effect by `attributes` (heterogeneous treatment effect) — reuses E4 targeting infra.
- **Live re-estimation** of remaining duration from accrued exposures.
- **Native review** of fr/zh/ar (today's verdict/interpretation strings were written without a native speaker).

## Deploy / gotchas (carried over)
- Deploy = `huggingface_hub.upload_folder(folder_path="D:/hfdeploy", repo_id="liovina/ab-test-research-designer", repo_type="space", token=<from git credential manager>, ignore_patterns=[".git/**","**/__pycache__/**","archive/**","docs/demo/*.png","*.sqlite3*","**/node_modules/**"])`. Snapshot from `git archive main | tar -x -C /d/hfdeploy`. Detect rollout by **change** of live `assets/index-<hash>.js` (HF build hash ≠ local).
- In Python scripts use **`D:/…` not `/d/…`** (Git Bash vs Windows-Python path mismatch, same as `/tmp`).
- Run vitest **serially** (`--no-file-parallelism`) on Windows — parallel runs give false failures from thrashing.
- EN backend verdict strings are pinned byte-for-byte by tests; change EN wording → update tests.
- Backend full suite ~11 min; on additive/frontend-only PRs the authoritative gate is CI (ubuntu/windows/verify-postgres).

## Budget
~300–500k tokens, one agent serially, local commits autonomously, deploy = external publish (owner gate unless told otherwise).
