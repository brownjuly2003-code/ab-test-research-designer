## Промпт 1: Оценка одного проекта

Скопировать, заменить `[PROJECT_PATH]` на путь к проекту.

---

```
## GOAL

Evaluate the project at [PROJECT_PATH] for GitHub public release readiness. Write report to github-readiness.md.

## WHAT TO DO

Read the entire project. Then fill in the template below with real data.

## HOW TO WORK

1. List all files and folders, understand the structure
2. Read key files: README, package.json/pyproject.toml/Cargo.toml, main entry points, tests, configs
3. Try to understand what the project DOES (not just what it contains)
4. Evaluate honestly — this assessment decides whether the project goes public

## OUTPUT TEMPLATE

# GitHub Readiness: [project name]

## What it is
- One-sentence description: [...]
- Problem it solves: [...]
- Target audience: [who would use this?]
- Tech stack: [languages, frameworks, key dependencies]

## Uniqueness
- Similar projects on GitHub: [list 3-5 closest alternatives if you can find them, or "search needed"]
- What makes THIS one different: [...]
- Would someone star this? Why? [honest answer]

## Completeness
| Aspect | Status | Details |
|--------|--------|---------|
| Core functionality works | [yes/partial/no] | [...] |
| Has README | [yes/no] | [quality: good/basic/missing] |
| Has tests | [yes/no] | [count, coverage estimate] |
| Has examples/docs | [yes/no] | [...] |
| Has license | [yes/no] | [which] |
| Has .gitignore | [yes/no] | [...] |
| No hardcoded secrets/paths | [yes/no] | [list any found] |
| No personal data | [yes/no] | [list any found] |
| Dependencies are standard | [yes/no] | [any unusual/private deps?] |

## Code quality
- Estimated quality: [1-10]
- Code style consistency: [consistent/mixed/messy]
- Architecture: [clean/acceptable/spaghetti]
- Comments/docs in code: [good/sparse/none]
- Language: [what language are comments/docs in? would need translation?]

## Before publishing (must fix)
| # | What | Severity | Effort |
|---|------|----------|--------|
[only things that MUST be fixed before going public — secrets, broken functionality, embarrassing code]

## Before publishing (should fix)
| # | What | Why | Effort |
|---|------|-----|--------|
[things that would make a better impression but aren't blockers]

## Scores
| Metric | Score (1-10) | Comment |
|--------|-------------|---------|
| Usefulness (does it solve a real problem?) | [...] | [...] |
| Uniqueness (is there already something better?) | [...] | [...] |
| Completeness (can someone use it as-is?) | [...] | [...] |
| Code quality | [...] | [...] |
| Documentation | [...] | [...] |
| **Overall GitHub-ready** | **[...]** | **[...]** |

## Verdict
[PUBLISH / FIX THEN PUBLISH / SKIP]
Reason: [1-2 sentences]

## CONSTRAINTS
- Be brutally honest — false positives waste time
- "Usefulness" matters more than "code quality" for GitHub
- A working ugly project > a beautiful empty skeleton
- If the project is half-done but the idea is strong, say so
- If there are secrets, credentials, personal paths — flag as CRITICAL
```

