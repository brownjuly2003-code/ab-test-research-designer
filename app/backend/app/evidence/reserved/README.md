# Reserved — not shipped

Nothing in this directory is imported by the running application, and nothing
here ships in the wheel (`[tool.setuptools.packages.find] exclude` in
`pyproject.toml`; `scripts/check_wheel_payload.py` fails the build if a
`reserved/` member appears in a wheel namelist).

It is kept, not deleted, because phase G needs it:

| Module | Kept for |
|---|---|
| `dbt_manifest.py` | Importing a dbt manifest as protocol lineage. Carries the pinned `dbt/manifest/v12.json` schema and its SHA-256, which is the expensive part to recover. |
| `legacy.py` | Converting a legacy project record into a frozen protocol, so the pre-Trialmark corpus can be replayed rather than retyped. |

Both are covered by their tests in `app/backend/tests/reserved/`, which stay in
the gate. A reserved module that stops compiling is a reserved module nobody
can revive, so the tests are the point of keeping it here rather than in Git
history.

If you are about to import something from here into `app/backend/app`, that is
the moment the module stops being reserved: move it back out, put it in the
wheel, and delete its row above.
