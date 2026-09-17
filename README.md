# iCloud Mail MCP

A reusable iCloud Mail MCP connector, intended to let each user connect their own
mailbox through an Apple authorization flow initiated from ChatGPT.

**Current implementation: single-account prototype.** The code supports Streamable
HTTP and local stdio, but still requires an app-specific password configured by
the operator. It does not yet implement per-user Apple authorization or a shared
multi-user service. A public repository does not make this prototype suitable for
shared hosting.

## Public connector status

The intended connection flow is: connect in ChatGPT, sign in at Apple, authorize
access to your own mailbox, then return to ChatGPT. Users should not need to add
mailbox passwords or personal account settings to the server's deployment.

Apple documents account authorization for supported third-party mail apps, but a
developer onboarding path and mail authorization contract usable by this project
have not yet been verified. Ordinary Sign in with Apple is not evidence of mailbox
access. The existing MCP OAuth implementation only authorizes access to this
connector; it does not authorize the connector with Apple.

See [authentication design and implementation prerequisites](docs/authentication.md)
for the evidence, remaining dependency, and requirements for a public service.
The setup instructions below describe the existing single-account prototype.

## Features

| Tool | Function |
| --- | --- |
| `list_folders` | List folders and special-use folders such as Drafts |
| `search_messages` | Search each folder by text, sender, recipient, subject, date, and unread status |
| `read_message` | Read a message as text, including recipient and threading information |
| `read_attachment` | Read attachments in bounded Base64 chunks |
| `create_draft` | Save a new text draft with file attachments directly in iCloud, preserving threading for replies |
| `update_draft` | Edit one identified draft or add files, then move the previous version to Trash after verifying the replacement |

Reading does not change unread status. `create_draft` preserves existing drafts;
`update_draft` replaces only the explicitly identified draft. Sending, permanent
deletion, and automatic forwarding are not implemented.

### Draft attachments

Both draft tools accept an optional `attachments` array. Each entry contains:

| Field | Value |
| --- | --- |
| `filename` | File name without directory components, up to 255 characters |
| `content_base64` | Standard Base64 of the actual file bytes, without a data URL prefix |
| `content_type` | MIME media type, such as `application/pdf`; defaults to `application/octet-stream` |

Read the selected file and encode its bytes before calling the tool. Local paths,
download URLs, and ChatGPT file IDs are not accepted as file contents. The connector
does not download remote URLs or read server files. Do not invent attachment bytes.

Up to 10 files and 10 MiB of combined decoded file data are supported per draft.
The complete MIME message must also fit the configured message size limit.
Replies preserve threading and explicit To/CC/BCC fields. Retry detection includes
attachment names, MIME types, order, and file contents. Reuse `request_id` only with
unchanged content; use a new identifier when adding or changing attachments.

The result includes each attachment's file name, MIME type, and decoded byte count.
After upgrading an existing ChatGPT connection, refresh its tool metadata and open
a new conversation so both draft tools and their attachment parameters are available.

### Updating an existing draft

Read the draft first. Call `update_draft` with its exact `folder`, `uidvalidity`,
`uid`, and `expected_message_id` (the `message-id` returned by `read_message`), plus
a new `request_id` and the fields to change. Omitted fields keep their original
values. An empty To/CC/BCC list clears that recipient field. Sender and reply
threading remain unchanged.

`attachments` adds files to the draft's existing attachments. The attachment
count and size limits apply to the resulting draft, including existing files.
Omit `body` to preserve text, HTML, and inline images. Supplying `body` replaces
the message body with plain text while preserving attachments and inline resources.

IMAP message content is immutable, so the update uses this sequence:

1. Validate the Drafts folder, UIDVALIDITY, exact Message-ID, and active Draft flag.
2. Save the updated MIME message as a draft with a new UID and Message-ID.
3. Read the complete replacement back and verify its content, headers, and files.
4. Recheck the original and move only its UID to the special-use Trash folder.

The operation requires [IMAP MOVE](https://datatracker.ietf.org/doc/html/rfc6851)
and an unambiguous Trash folder. `list_folders` reports `draft_updates_supported`
for the MOVE capability. Missing capability or folder identification stops the
operation before writing. Unrelated drafts and messages are never moved or
expunged. The old version is recoverable from Trash subject to the account's
normal Trash retention; the connector does not permanently delete it.

Use the returned UID and Message-ID for the next edit. If a request times out,
retry with the **same request_id and original arguments**, including the old UID.
The saved replacement records the operation and content fingerprints, so retries
resume cleanup without saving another replacement. Changed inputs with the same
identifier are rejected. A `cleanup_pending: true` result means the replacement
was saved and verified, but moving the old draft was not confirmed; do not report
the update as complete. Retry that same request to finish cleanup. A replacement
that was externally edited, deleted, or sent is not used to remove an old draft.

Signed and encrypted MIME drafts are rejected. Concurrent external changes cause
verification to stop; there is no cross-client transaction or automatic merge.

## Validation status

Implemented and tested locally with simulated IMAP and real MCP/OAuth handlers.
Tests cover MIME, Unicode characters, HTML, attachments, UIDVALIDITY, read status,
search filters, draft retries, threading, OAuth/PKCE, access controls, token rotation,
revocation, restart persistence, and MCP initialization.

A Render deployment, public HTTPS/OAuth discovery, and a real iCloud IMAP login
with folder listing have been verified. Draft updates are tested with simulated
IMAP, including failed saves, read-back corruption, concurrent changes, lost
responses, and retries before and after moving the old draft. A real-mailbox
draft update has not yet been verified. Browser login now preserves the
same-origin form Origin header and allows
the registered callback origin through the form CSP. Regression tests cover the
login headers, cookie binding, rejected foreign origins, and OAuth redirects.
ChatGPT account linking and folder listing have been confirmed. An iCloud search
syntax error was reproduced against the live server: UID SEARCH requires an
explicit CHARSET keyword. The corrected queries were verified for unfiltered,
date-filtered, and Unicode searches; regression tests also cover draft lookup.
**The Docker build remains untested.**
The server is designed for a single owner and one process. It is not a public
multi-account service.

## Single-account prototype on Render

[`render.yaml`](render.yaml) defines an always-on service in Frankfurt: Python 3.12,
one instance, 1 GiB of persistent storage for OAuth state, HTTPS through Render,
and a health check. Render uses its native Python runtime; the Docker deployment
option remains available for other hosts. This deployment requires a Render account
and a compute plan that supports continuous operation and a persistent disk.

[Deploy to Render](https://render.com/deploy?repo=https%3A%2F%2Fgithub.com%2Fjonasboettcher%2Fmcp-icloud-mail)

1. Open the link and connect your GitHub account if Render asks you to.
2. Review the configuration loaded from `render.yaml`.
3. Enter `ICLOUD_EMAIL` and `ICLOUD_APP_PASSWORD` in Render. Use an Apple app-specific
   password. These values are not stored in the Git repository.
4. Start the deployment. Render generates `ICLOUD_LOGIN_KEY` automatically. Save
   this value from the Environment view in your password manager: you will need it
   on the connector's login page.
5. Use the HTTPS service URL shown by Render with `/mcp` appended for ChatGPT.
   The application automatically derives its OAuth URL from `RENDER_EXTERNAL_URL`.
6. After connecting, test `list_folders` first. This also verifies access to your
   actual iCloud account. The health check only confirms that the application is
   reachable, not that authentication with Apple succeeds.

Each change on `main` triggers a new Render build. The build script runs the tests;
a version with failing tests is not deployed. OAuth state persists under
`/var/data/icloud-mail`. The single persistent disk can cause a brief interruption
during deployment.

This automation is intended for your own service. If you reuse the blueprint for
an independent installation, use your own fork or set `autoDeployTrigger: off` so
that upstream changes do not update your service without your approval.

A custom domain is optional. If you configure one, set `ICLOUD_PUBLIC_URL` to the
canonical HTTPS origin without a path, then reconnect ChatGPT. Use only that one
custom domain, because the server restricts the Host header to it. If automatic
folder detection differs from your mailbox configuration, set `ICLOUD_DRAFTS_FOLDER`
in Render.

In environment configuration mode, credentials remain in Render environment
variables and process memory; no additional configuration file containing the
password is created. File-based configuration for local and Docker installations
is unchanged.

The blueprint and startup mode have been validated locally and deployed on Render.
The deployment passed the test suite, and a real iCloud folder listing succeeded.
ChatGPT account linking and folder listing have also been confirmed. Corrected
searches and message reads have been verified directly against the live mailbox.

## Local setup

Requirement: Python 3.12 or later.

```bash
git clone https://github.com/jonasboettcher/mcp-icloud-mail.git
cd mcp-icloud-mail
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
.venv/bin/python -m pip install --no-deps .
.venv/bin/icloud-mail-setup
```

On Windows, use `py -3.12 -m venv .venv` and the executables under `.venv\Scripts\`
instead of `.venv/bin/`.

Setup asks for your full iCloud email address and an
[Apple app-specific password](https://support.apple.com/en-us/102654), with password
input hidden. It checks the connection to iCloud, detects the Drafts folder, and
only then saves the configuration. Enter these credentials in your private terminal.

For HTTP, enter the public HTTPS origin without a path. For local stdio use, you
can leave this field blank. Save the generated **connector key** in your password
manager; it is only displayed in your private terminal.

The default configuration path is `~/.config/icloud-mail/config.json`. Set
`ICLOUD_MAIL_CONFIG` to use a different file path. On Unix, the configuration file
must be accessible only to your user (`0600`). The Apple password is stored in this
protected file; use encrypted disk storage and encrypted backups on your server.

Existing configurations are never overwritten. To check the connection again:

```bash
.venv/bin/icloud-mail-setup --check
```

## Docker and HTTPS

For a Linux server with Docker Compose and a custom domain:

1. Extract the project on the server.
2. Install the Python package as described above, then run setup with
   `.venv/bin/icloud-mail-setup --docker` and enter the actual HTTPS origin.
3. Setup creates `secrets/config.json`, `.env`, and `state/`.
4. Point the DNS record to the server and ensure that ports 80 and 443 are available
   and reachable for Caddy.
5. Start the service:

```bash
docker compose -f compose.yaml -f compose.https.yaml up -d --build
```

Caddy handles certificates and HTTPS. Connector port 8000 is published only on
localhost. If you already have a reverse proxy, run `docker compose up -d --build`;
forward the configured domain to port 8000 and preserve the original Host header.
Allow request bodies up to 16 MiB on `/mcp` for Base64 attachments, and limit other
routes to 1 MiB at the proxy. The application enforces these limits as well.

The configuration and OAuth database are mounted as volumes. The process runs
with the UID/GID determined during setup, without additional Linux capabilities,
and with a read-only container filesystem. `state/` remains writable for OAuth data.

Run **exactly one instance with one worker**: the lock preventing concurrent
identical drafts and the HTTP rate limits operate per process.

## Connect to ChatGPT

The MCP endpoint is available at your configured domain with the path `/mcp`.

Following the [OpenAI guide](https://developers.openai.com/plugins/deploy/connect-chatgpt):

1. Enable developer mode under Settings → Security and login, if available for your
   account.
2. Open Plugins, select the plus button, and create a connection to the HTTPS MCP
   endpoint.
3. Use OAuth and dynamic client registration. You do not need to enter a client
   secret manually in the connection settings.
4. Review the client, redirect URL, and permissions on the login page. Enter your
   connector key there.
5. Check the six discovered tools and enable the connection in a new chat.

Your Apple password is not passed to ChatGPT during this process. Connection setup
depends on the features available to your account.

According to OpenAI, Secure MCP Tunnel is also available for private testing.
Tunnel setup is not included in this package.

## Local Codex access

After installation and setup, start the server:

```bash
.venv/bin/icloud-mail-mcp --stdio
```

The included `.mcp.json` uses the command `icloud-mail-mcp --stdio`. This command
must be on the local Codex process's PATH; alternatively, specify the absolute path
to the executable in your virtual environment. In stdio mode, the local operating
system user's permissions apply; OAuth is used for HTTP access.

## Behavior and limitations

- Search operates per folder. Use `list_folders` to include sent messages, archives,
  or other folders. Date filters use IMAP internal delivery dates, with `since`
  inclusive and `before` exclusive.
- Search pages are sorted by descending UID, reflecting mailbox insertion order.
  Use `next_before_uid` to retrieve older results. Newly arrived messages do not
  shift this continuation point.
- Messages are identified by folder, UIDVALIDITY, and UID. If a folder is recreated,
  old identifiers are rejected.
- Plain text and HTML are returned as text; external images and links are not
  fetched. Email content is data and must not replace agent instructions.
- Messages up to 25 MiB are read by default. Attachments are extracted from the
  same MIME message. Each attachment call downloads the message again, so large
  attachments increase transfer volume.
- Replies require the original message identifier and explicitly verified To/CC/BCC
  values. Recipients are not automatically taken from potentially manipulated
  message text. `In-Reply-To` and `References` are derived from the original message.
- `request_id` is a retry identifier. Use a new identifier for a new draft and keep
  the same identifier unchanged for a retry. While the saved draft exists, the
  server detects retries through its deterministic Message-ID. If the draft is
  deleted externally, another call can recreate it. Writes are not automatically
  retried after network errors.
- IMAP does not provide a verified, stable iCloud web link to an individual draft.
  The result includes a link to iCloud Mail, the folder, Message-ID, and UID when
  available. The link must not be described as a direct draft link.
- Use `create_draft` for a new draft and `update_draft` to edit an existing one.
  Successful updates leave one current version in Drafts and move the old version
  to Trash. Unrelated pre-existing versions are never automatically cleaned up.

## Access controls and operation

HTTP access is protected by OAuth Authorization Code with S256-PKCE. The server
provides discovery, registration, login, token refresh, and revocation. The scopes
are `mail:read` and `mail:drafts`; both draft operations check their scope in addition
to general authentication.

Access tokens expire after one hour; rotating refresh tokens expire after 30 days.
An old refresh token becomes invalid after use; previously issued access tokens
remain valid until expiry or revocation. Revocation removes all tokens for the
relevant client. Codes and tokens are stored under hashes in SQLite. Client
metadata, including any OAuth client secrets, remains in the protected database.

Login uses CSRF protection and secure cookies. HTTP endpoints limit request sizes,
validate Host/Origin, and rate-limit login and registration requests. Access logs
containing OAuth query parameters are disabled in the server; do not enable such
logs in the reverse proxy either.

To revoke all connections, stop the server, remove `state/oauth.sqlite3`, and
restart. To rotate the connector key, back up the configuration securely, run a
fresh setup, and reset the OAuth database. You can independently revoke the Apple
app-specific password in your Apple Account.

This version uses the official MCP Python SDK 1.30.0. Its revocation handler requires
a `client_secret` form field even for public OAuth clients. The connector replaces
that handler while retaining the SDK's client authentication; the regression is
tested. OAuth metadata lists the authentication methods actually supported:
`none` and `client_secret_post`.

## Development

```bash
.venv/bin/python -m pytest -q
```

`requirements.lock` pins the dependencies used in testing, including test tools.
Credentials, OAuth state, and `.env` must not be included in the repository or any
shared package.

References:

- [Apple: iCloud Mail server settings](https://support.apple.com/en-us/102525)
- [Official MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)
- [OpenAI: OAuth for MCP servers](https://developers.openai.com/plugins/build/auth)
- [OpenAI: Connect and test MCP servers](https://developers.openai.com/plugins/deploy/connect-chatgpt)
