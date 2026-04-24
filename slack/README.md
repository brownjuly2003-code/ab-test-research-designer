# Slack App

This folder contains the distributable Slack App manifest for the two-way integration.

## Install

1. Replace `{DEPLOY_HOST}` in `app-manifest.yml` with the public HTTPS host that serves the FastAPI backend.
2. Import the manifest in Slack UI: **Create New App** -> **From an app manifest**.
3. Copy the app credentials into runtime secrets:

```bash
AB_SLACK_CLIENT_ID=...
AB_SLACK_CLIENT_SECRET=...
AB_SLACK_SIGNING_SECRET=...
```

4. Restart the backend and open `/slack/install`, or use the Slack App tile in the sidebar.
5. In Slack, run `/ab-test projects` to verify slash-command delivery.

`AB_SLACK_WEBHOOK_URL` can still be used for the older one-way webhook flow; the Slack App flow stores OAuth bot tokens in `slack_installations`.

## Validate

If the Slack CLI is available:

```bash
slack manifest validate --manifest slack/app-manifest.yml
```

If the CLI is not available, import the manifest through the Slack UI and check that the slash command, OAuth redirect URL, interactivity URL, and events URL are accepted.
