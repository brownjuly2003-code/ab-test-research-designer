# Security Policy

## Supported versions

| Version | Supported |
|---|---|
| latest release (`v*` tags) | yes |
| `main` | yes |
| older releases | no — upgrade to the latest release |

## Reporting a vulnerability

Please **do not open a public issue** for security problems.

Use GitHub private vulnerability reporting: **Security → Report a vulnerability** on this
repository. You should receive an initial response within 7 days. Please include reproduction
steps, the affected endpoint or module, and the impact you see.

## Threat model notes

This is a **local-first** tool; the documented threat model and its accepted trade-offs live in
[`docs/RUNBOOK.md`](docs/RUNBOOK.md) and [`docs/PRODUCTION.md`](docs/PRODUCTION.md). Highlights:

- The public demo Space runs read-only anonymous sessions (`AB_PUBLIC_DEMO=true`, `AB_ENV=demo`);
  mutations require an operator token.
- Webhook deliveries enforce an SSRF guard (non-public target addresses are refused) everywhere
  except the explicit `AB_ENV=local` development posture.
- Slack bot/user tokens are stored unencrypted in the local database by design under the
  local-first model; hosted setups get explicit hardening guidance in the RUNBOOK.
- The operator session token is kept in `sessionStorage` (tab-scoped, cleared on tab close)
  rather than a cookie — an accepted trade-off: CSP (`script-src 'self'`) mitigates XSS
  exfiltration, and the token never persists to disk. CodeQL flags this pattern; the alert is
  dismissed with this rationale.
- `AB_ENV=production` fail-fast requires PostgreSQL and configured auth tokens.
- Issued API keys are **read** or **write** only. Operator surfaces (`/api/v1/keys`,
  `/api/v1/webhooks`) require the static `AB_ADMIN_TOKEN`; a database key never grants
  operator access (legacy `scope=admin` keys are normalized to `write` on startup).

## Dependency and code scanning

CI gates every push with `pip-audit`, `npm audit --audit-level=high` (both package roots),
Trivy image scans before Docker publish, and CodeQL analysis for Python and TypeScript.
