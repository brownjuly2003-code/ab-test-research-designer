# Slack App Report

## Implemented

- Added `slack/app-manifest.yml` and `slack/README.md`.
- Added Slack OAuth install/callback, slash commands, interactive actions, events stub, and status endpoint.
- Added Slack request signature verification with five-minute replay protection.
- Added `slack_installations` storage for SQLite and Postgres-backed runtimes.
- Added a sidebar Slack App tile with install/status display.

## Tests

Targeted backend command:

```bash
python -m pytest -p no:schemathesis app/backend/tests/test_slack_signature.py app/backend/tests/test_slack_service.py app/backend/tests/test_slack_routes.py
```

Latest targeted result: 11 passed.

Full verification:

```bash
cmd /c scripts\verify_all.cmd --with-e2e
```

Latest full result: exit 0; backend tests inside wrapper reported 322 passed.

## Smoke

Slack UI import screenshot was not taken in this environment. Validate with Slack UI import or:

```bash
slack manifest validate --manifest slack/app-manifest.yml
```

After installing into a test workspace, run:

```text
/ab-test projects
```
