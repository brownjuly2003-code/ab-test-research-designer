# Slack

AB Test Research Designer supports two Slack paths:

- one-way incoming webhook delivery for audit notifications
- a two-way Slack App with OAuth install, `/ab-test` slash commands, and interactive analysis actions

## Slack App Setup

Create a Slack App from `slack/app-manifest.yml`, replacing `{DEPLOY_HOST}` with the public HTTPS backend host.

Set these backend secrets:

```bash
AB_SLACK_CLIENT_ID=...
AB_SLACK_CLIENT_SECRET=...
AB_SLACK_SIGNING_SECRET=...
```

Open `/slack/install` or use the Slack App tile in the sidebar. After OAuth completes, the backend stores the workspace installation in `slack_installations`.

## Commands

```text
/ab-test projects
/ab-test status <project_id>
/ab-test run <project_id>
```

Slack request signatures are verified with `AB_SLACK_SIGNING_SECRET` and a five-minute replay window.
