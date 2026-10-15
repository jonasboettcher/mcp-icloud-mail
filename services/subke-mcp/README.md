# Subke MCP on Render

Private MCP bridge for the Subke Customer API, with 16 read operations, 4 write operations, and connection_status. Uses Node.js built-ins only; no runtime dependencies.

This is a single-owner Subke connector deployed independently from the iCloud and Lexware services in the same repository. It does not offer per-user Subke account isolation.

## Render configuration

- Runtime: Node 24
- Region: Frankfurt
- Plan: Free
- Repository branch: subke-mcp
- Source directory: services/subke-mcp
- Build: cd services/subke-mcp && npm ci && npm test
- Start: cd services/subke-mcp && npm start
- Health check: /healthz
- MCP endpoint: /mcp (Streamable HTTP, JSON responses)

Free Render services may sleep after inactivity.

## Required secrets

Set these in the Render service environment, never in Git or a plugin archive:

- MCP_ACCESS_TOKEN: a random connection key of at least 32 characters, independent of Subke credentials.
- SUBKE_API_KEY: the customer API key created in Subke.
- SUBKE_WRITE_ENABLED=true enables write operations.

The protected MCP endpoint returns 401 without the connection key. Health and the landing page contain no Subke records. Redirects from the Subke API are rejected. Write operations are not retried automatically.

## Client connection

Use https://<actual-service-host>/mcp and Bearer authentication with MCP_ACCESS_TOKEN. The private OpenAI plugin declares API-key authentication; the credential is entered during connection setup and is excluded from the plugin archive.

The MCP connection key is not the Subke key.

## Verification

Run npm test. After deployment, check /healthz, confirm unauthenticated /mcp requests are denied, initialize the authenticated MCP connection, and call list_warehouses or another read operation. Do not create live fulfillment data as a connectivity test.

## Source

The API tool catalog is derived from references/subke-openapi.json downloaded from the Subke customer portal. The original Sites-only deployment files are not included.
