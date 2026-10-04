# Lexware Office MCP on Render

Dedicated Render service in Jonas Böttcher's existing workspace. Source and
deployment use the isolated `lexware-mcp` branch. The mail service remains on
`main`.

Based on [marselsel/Lexware-MCP-Server](https://github.com/marselsel/Lexware-MCP-Server),
pinned to `8da792d08146665036943a9ee7d1b7f444225939`. The single-owner OAuth
provider is adapted from the iCloud project with separate keys, scopes and
storage. It does not access the mail account.

## Render settings

- Frankfurt region; Node runtime; `lexware-mcp` branch; automatic deployments off.
- Build: `bash lexware_gateway/build.sh`
- Start: `.lexware-venv/bin/python -m lexware_gateway.server`
- Health: `/healthz`; MCP: `/mcp`; OAuth dynamic client registration and PKCE.
- `NODE_VERSION=24.19.0`
- `LEXWARE_LOGIN_KEY`: independent random connector key, at least 32 characters.
- `LEXWARE_API_KEY`: generate in the [Lexware API settings](https://app.lexware.de/addons/public-api)
  and store only as a secret Render environment variable.

Deploy after configuring the API key. Without it, service health, OAuth and tool
discovery work, but all tool invocations are blocked before accessing Lexware.
Health reports `lexware_configured` without exposing credentials.

## ChatGPT connection

Use the service's `/mcp` URL and OAuth authentication. Enter `LEXWARE_LOGIN_KEY`
on the connector's authorization page. Never put the Lexware API key into
ChatGPT, GitHub or a plugin package.

## Scope and the 2024 workflow

The 17 registered tools provide targeted document, voucher, file, contact,
payment and profile reads; bookkeeping voucher creation and updates; and file
uploads and attachments. Sales-invoice creation, invoice correction creation,
article writes, webhook writes and deletion tools are excluded from the actual
registered list.

The [export-based 2024 checklist](https://github.com/tradmusica/organisation/blob/main/processes/lexware-checkliste-2024-exportbasiert.md)
remains authoritative. No live substantive bookkeeping audit. Corrections must
follow a verified instruction in `03_Korrekturen`, with version and outcome
checks. Bank allocations, cancellations and locked vouchers still require the
Lexware web interface.

## Operation and OAuth state

The initial deployment uses Render's free plan. New registrations have encrypted
self-contained client IDs under RFC 7591 A.5.2. Client metadata, including any
client secret, stays encrypted inside the ID; the server validates it using a
stable key derived from `LEXWARE_LOGIN_KEY` and the public endpoint. These IDs
survive filesystem resets without a new paid service. IDs expire after one year;
changing the connector key or endpoint invalidates them.

Legacy UUID client IDs are still accepted when their original SQLite records
exist. A UUID whose record was lost cannot be reconstructed safely from the ID
alone. ChatGPT reuses its registered client credentials, so clicking reconnect
may reuse the lost ID. The OAuth client registration must be renewed or its
original metadata restored from a backup.

Authorization codes, access tokens, refresh tokens and pending login flows still
use SQLite on the temporary filesystem. After a restart or deployment, authorize
again with the surviving client registration. To retain all OAuth state across
deployments, use a persistent disk at `/var/data` and
`LEXWARE_STATE_DIR=/var/data/lexware-oauth`. The optional
`lexware_gateway/render.yaml` describes that configuration. Run exactly one
instance. Never version credentials or OAuth databases.

## Verification

Run the unchanged upstream tests before patching, then the TypeScript build and
gateway tests. Gateway coverage includes empty-filesystem registration recovery
for public and confidential clients, PKCE, callback binding, client-secret checks,
tampering, expiry, key/endpoint isolation, CSRF, token rotation, missing-key
blocking, and the actual MCP tool list. Tests do not create live bookkeeping
entries.
