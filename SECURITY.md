# Security Policy

## Supported Versions

Argus is pre-1.0 and under active development. Only the latest `main` is supported.

| Version | Supported          |
| ------- | ------------------ |
| 0.x     | :white_check_mark: |

## Reporting a Vulnerability

If you discover a security vulnerability, please report it responsibly:

1. **Do not** open a public issue.
2. Use GitHub's [private vulnerability reporting](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing-information-about-vulnerabilities/privately-reporting-a-security-vulnerability)
   on this repository, or email the maintainer directly.
3. Include: a description, steps to reproduce, potential impact, and a suggested fix
   if you have one.

You can expect an initial response within a few days.

## Security Considerations

Argus handles credentials and has read/write access to your network's source of truth:

- **NetBox API token** (`NETBOX_TOKEN`) grants whatever NetBox permissions the token
  was issued with. Scope it to the minimum required; prefer read-only tokens until
  reconciliation write paths are enabled and trusted.
- **Discovery collectors** will hold device/controller credentials (UniFi, SNMP, SSH).
  These are resolved from environment variables / secret files, never committed.
- **Reconciliation writes** are **dry-run by default** and **confirmation-gated** —
  an agent cannot mutate NetBox without an explicit, separate confirmation step.

### Best practices

1. Use environment variables or a secrets manager for `NETBOX_TOKEN` and collector
   credentials — never hardcode them or commit `.env`.
2. Start with a **read-only** NetBox token. Only widen scope once you trust the
   reconciliation behavior in dry-run.
3. Run the HTTP server bound to a trusted interface, and set `HTTP_TOKEN` to require
   `Authorization: Bearer <token>` on `/api` and `/webhooks` for any exposed deployment
   (unset = open; `/health` stays public).
4. Review the dry-run reconcile plan before confirming any apply.

## Supply Chain

- Dependencies are kept current via Dependabot (pip, npm, GitHub Actions).
- Changes land via signed-commit pull requests with required status checks.
