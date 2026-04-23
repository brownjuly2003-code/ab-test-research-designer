# GitHub Readiness: AB Test Research Designer

## What it is
- One-sentence description: A local-first web app for planning A/B and multivariant experiments, calculating sample size and duration, generating deterministic reports, and storing project history in SQLite.
- Problem it solves: It replaces ad-hoc spreadsheets and fragmented experiment planning with a single local workflow for experiment design, feasibility checks, warnings, reporting, and project history.
- Target audience: Growth PMs, product analysts, experimentation engineers, and small teams or solo builders who want a self-hosted/local experiment planning tool.
- Tech stack: Python, FastAPI, Pydantic, SQLite, React 19, TypeScript, Vite, Pytest, Vitest, Playwright, Docker.

## Uniqueness
- Similar projects on GitHub: [growthbook/growthbook](https://github.com/growthbook/growthbook), [spotify/confidence](https://github.com/spotify/confidence), [zalando/expan](https://github.com/zalando/expan), [PlaytikaOSS/abexp](https://github.com/PlaytikaOSS/abexp), [welpo/ab-test-calculator](https://github.com/welpo/ab-test-calculator).
- What makes THIS one different: It is not just a stats library and not a full experimentation platform. Its niche is a local-first planning workspace with deterministic math, heuristic warnings, optional local LLM advice kept separate from the hard-math output, SQLite-backed project/history storage, workspace backup/import, and report export.
- Would someone star this? Why? Honest answer: yes, some people would, especially if they want a lightweight self-hosted planner instead of a full SaaS experimentation stack. It is less likely to attract broad stars from teams that expect production traffic allocation, result ingestion, or warehouse-native experiment analysis.

## Completeness
| Aspect | Status | Details |
|--------|--------|---------|
| Core functionality works | yes | `python scripts/verify_all.py` exited `0` on 2026-04-02. The standard pipeline checked generated artifacts, workspace backup roundtrips, backend tests, benchmark, and frontend verification through the Windows wrapper. |
| Has README | yes | quality: good, but currently weakened by broken GitHub-facing absolute local links and Windows-specific absolute paths. |
| Has tests | yes | At least 176 tests/specs visible from the repo: 109 backend pytest tests passed in verification, plus 66 frontend unit specs and 1 Playwright E2E spec in source. Exact coverage percentage is not measured, but core flows look medium-high coverage. |
| Has examples/docs | yes | Strong docs set: README, API, architecture, rules, runbook, release checklist, sample payload, and demo screenshots. |
| Has license | no | No `LICENSE` file found at repo root. This is a real publish blocker. |
| Has .gitignore | yes | Good baseline coverage for Python, Node, caches, build outputs, DB files, exports, and smoke artifacts. |
| No hardcoded secrets/paths | no | No real secrets found in reviewed tracked files, but hardcoded local paths exist in `.env.example`, `README.md`, and `docs/RUNBOOK.md`. README also contains absolute local markdown links like `/D:/AB_TEST/...`, which will be broken on GitHub. |
| No personal data | yes | No credentials or obvious personal data found in the reviewed tracked project files. |
| Dependencies are standard | yes | Public and normal stack: FastAPI, React, Vite, Pydantic, Pytest, Vitest, Playwright, Docker. Optional local LLM endpoint is runtime-configured, not a private package dependency. |

## Code quality
- Estimated quality: 8/10
- Code style consistency: consistent
- Architecture: acceptable
- Comments/docs in code: sparse
- Language: English in code and docs; no translation is required before publishing

## Before publishing (must fix)
| # | What | Severity | Effort |
|---|------|----------|--------|
| 1 | Add a real open-source license file at repo root | Critical | Small |
| 2 | Remove hardcoded local absolute paths and broken absolute markdown links from `README.md`, `.env.example`, and `docs/RUNBOOK.md`; replace them with repo-relative links and machine-agnostic examples | Critical | Small |
| 3 | Cut a clean release snapshot before publishing; the current worktree is dirty and includes many modified/untracked release-adjacent files, so there is no single clearly audited public snapshot yet | High | Small |

## Before publishing (should fix)
| # | What | Why | Effort |
|---|------|-----|--------|
| 1 | Add POSIX/Linux command examples alongside Windows `set` / `cmd` flows | Public GitHub users will expect cross-platform docs, and the project already claims cross-platform verification entrypoints | Small |
| 2 | Split very large orchestration files such as `app/frontend/src/App.tsx`, `app/backend/app/main.py`, and `app/backend/app/repository.py` | The current architecture is workable, but these large files are maintainability hotspots | Medium |
| 3 | Add `CONTRIBUTING.md` and a short roadmap/non-goals section | This would make the repo feel more intentional and contributor-friendly on first contact | Small |
| 4 | Sharpen README positioning against larger platforms like GrowthBook | This project is stronger as a focused local planner than as a generic "A/B testing platform"; clearer positioning would improve first impression and starability | Small |

## Scores
| Metric | Score (1-10) | Comment |
|--------|-------------|---------|
| Usefulness (does it solve a real problem?) | 8 | Useful for teams that need disciplined local experiment planning without a full experimentation platform. |
| Uniqueness (is there already something better?) | 7 | The local-first planner/report/history combination is less common, but larger open-source experimentation platforms and analysis libraries already exist. |
| Completeness (can someone use it as-is?) | 8 | Feature set, docs, CI, Docker, and verification are strong; publishing blockers are mostly release hygiene and repo presentation. |
| Code quality | 8 | Consistent, tested, and reasonably structured, though some central files are too large. |
| Documentation | 6 | There is a lot of documentation, but the public-facing README currently has broken local links and Windows-specific absolute paths. |
| **Overall GitHub-ready** | **6** | **Strong project substance, but not ready for a public release until license and path/link issues are fixed.** |

## Verdict
[FIX THEN PUBLISH]
Reason: The project has real substance, good docs, CI, Docker support, and a serious verification story. But missing licensing and GitHub-breaking local path/link issues are hard blockers for a public release, even though they are easy to fix.
