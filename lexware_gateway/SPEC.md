# Lexware MCP for Verlag der Spielleute

Jonas authorized reusing the GitHub → Render setup on 2026-10-04.
The mature marselsel/Lexware-MCP-Server implementation is pinned to commit
8da792d08146665036943a9ee7d1b7f444225939. It provides the schemas, rate limiting,
voucher read-modify-write and file handling. A build-time allowlist excludes
sales-document creation, invoice corrections, unrelated writes and deletion.

ChatGPT connects over OAuth/PKCE, reusing the single-owner iCloud provider with
separate scopes, key, database and endpoint. The gateway forwards authenticated
MCP requests to a private backend protected by a random per-process token.
There is no connection to the mail account. Core actions: obtain targeted
exports, read exact documented correction targets, create/update bookkeeping
vouchers and attach original evidence. No additional UI is required.

LEXWARE_API_KEY belongs in Render environment settings. Without it, discovery
works but every tool invocation is blocked before any upstream API request.
LEXWARE_LOGIN_KEY authorizes ChatGPT connections and is a separate credential.
New client registrations use encrypted self-contained client IDs, as permitted
by RFC 7591 A.5.2. The encryption key is derived from LEXWARE_LOGIN_KEY and bound
to the public endpoint. Registrations survive a destroyed ephemeral filesystem;
callback validation, PKCE and confidential-client secret checks remain enforced.
Changing the login key or public endpoint invalidates these registrations.
Existing UUID registrations are supported only while their metadata remains in
the database; a lost UUID cannot be recovered from the ID alone. ChatGPT reuses
client credentials, so a new login is not a replacement for client registration.
Access tokens, refresh tokens and pending flows still use SQLite. After an
ephemeral restart, the user must authorize again using their surviving client ID.
An optional persistent disk at /var/data with
LEXWARE_STATE_DIR=/var/data/lexware-oauth also preserves that OAuth state.

2024 uses the current export-based handbook process. This infrastructure task
does not execute bookkeeping corrections. API limits require the web interface
for bank allocation, voucher cancellation and locked-period corrections.
