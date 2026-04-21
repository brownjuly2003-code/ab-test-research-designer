# v1.0.0 — A/B Test Research Designer

## Demo Links

- Hosted demo: `<placeholder — fill after fly deploy>`
- Docker image: `<placeholder — after docker push>`

## Executive Summary

v1.0.0 is the first stable release of AB Test Research Designer. It brings the full BCG Phase 1..5 wave into a single supported baseline: teams can define experiment inputs, review deterministic statistical guidance, save project history locally, and export decision-ready reports from one workspace.

This release also turns the product from an internal prototype into a releasable local tool. The frontend was reworked into a more navigable dashboard, project workflows gained templates, filters, revisions, and audit visibility, and the statistical surface now covers SRM checks, Bayesian sizing, sequential monitoring, CUPED, and guardrail planning.

Operationally, v1.0.0 adds stronger release hygiene around accessibility and quality gates. Automated axe coverage now spans the major interactive surfaces, Lighthouse CI is wired into the shipped frontend flow, and the verify pipeline remains the required gate before any future release or push.

## Capability Matrix

| Feature | Status | Notes |
| --- | --- | --- |
| Experiment design wizard and deterministic sample-size planning | GA | Stable for local experiment planning across the main wizard flow |
| Statistical decision support: SRM, Bayesian, sequential, CUPED, guardrails | GA | Exposed through the backend API and surfaced in the redesigned results UI |
| Saved projects, revisions, filters, templates, and audit log | GA | Local SQLite workspace with revision history and operational traceability |
| Report export: HTML, Markdown, PDF, CSV, XLSX | GA | Supports both immediate shareable exports and stored project report downloads |
| Accessibility and Lighthouse quality gates | GA | Automated axe and Lighthouse CI coverage are part of the release hardening path |
| AI advice via the local orchestrator adapter | Beta | Optional capability; deterministic planning works without it |
| Docker packaging for local deployment | Beta | Supported for local verification, but production hosting still needs external TLS termination |

## Known Limitations

- AI advice depends on a separately running local orchestrator reachable through `AB_LLM_BASE_URL`; when it is unavailable, the deterministic planning path remains available but advisory output is limited.
- Automated axe checks are in place, but manual screen-reader regression passes were not completed for this release.
- The provided Docker runtime does not enable HTTPS by default; production deployments still need a reverse proxy or platform-managed TLS in front of the container.
- Fly.io demo hosting is prepared as a single-machine SQLite deployment; horizontal scaling needs Postgres or LiteFS and is out of scope for v1.0.0.

## Upgrade Path

No migration required - v1.0.0 is the first stable release.

## Verification Steps For Publishing

1. Confirm the hosted demo placeholder now points at the live Fly URL and that `/health`, `/readyz`, and `/api/v1/diagnostics` return `200`.
2. Confirm the Docker image placeholder now points at the pushed registry tag or digest.
3. Re-run `scripts\verify_all.cmd --with-e2e`.
4. Attach the assets listed below.
5. Replace any remaining placeholders before clicking **Publish release**.

## Verification Commands

```powershell
python scripts/generate_api_docs.py --check
scripts\verify_all.cmd --with-e2e
scripts\verify_all.cmd --with-docker
```

## Assets To Attach

- `ab-test-research-designer_1.0.0.tar.gz` (repo HEAD tarball plus `fly.toml`)
- `docs/RELEASE_NOTES_v1.0.0.md`
- `docs/DEPLOY.md`

# How to publish

```bash
gh release create v1.0.0 --draft --notes-file docs/RELEASE_NOTES_v1.0.0-github-draft.md
```
