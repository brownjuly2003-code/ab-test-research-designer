# 2026-04-23 Postgres backend report

## Test delta

- Default SQLite backend suite: `311 passed` via `python -m pytest -p no:schemathesis app/backend/tests/ -q --basetemp .pytest-tmp`
- New Postgres-focused smoke coverage: `6 passed` via `python -m pytest -p no:schemathesis app/backend/tests/test_postgres_backend.py -q --basetemp .pytest-tmp`
- Scope added in this change:
  - backend factory and wrapper selection
  - Postgres CRUD/query smoke coverage
  - concurrent write smoke coverage
  - startup/snapshot gating for Postgres
  - Postgres readiness checks

## Benchmarks

Local p95 latency, single-user case, 200 seeded projects:

| Operation | SQLite p95 | Postgres p95 |
| --- | ---: | ---: |
| `get_project` | `3.312 ms` | `4.605 ms` |
| `list_projects` | `11.010 ms` | `11.078 ms` |
| `query_projects(metric_type="binary")` | `7.249 ms` | `8.484 ms` |

Result:

- Postgres stayed within the acceptance guard for single-user usage
- worst observed regression in this local run was `~1.39x` on `get_project`
- `list_projects` was effectively flat between backends in the local benchmark

## CI runtime impact

- Existing SQLite backend suite runtime in local verification: `208.92 s`
- New Postgres smoke suite runtime in local verification: `29.70 s`
- Expected GitHub Actions impact:
  - roughly `+30-90 s` for the new job after warm image cache
  - potentially `+1-2 min` on cold runners because of Postgres image/bootstrap overhead

## Notes

- SQLite remains the default path when `AB_DATABASE_URL` is unset
- HF snapshot sync is intentionally skipped for Postgres runtimes
- CI still keeps the original default verification job for SQLite; Postgres is covered by a dedicated Ubuntu smoke job
