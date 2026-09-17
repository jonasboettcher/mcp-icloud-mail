# Public connector authentication

Status: design target; upstream mail authorization is not yet verified.
Source review: 2026-09-17.

## Connection flow

1. A user starts connecting the MCP service from ChatGPT.
2. The connector starts that user's authorization flow with Apple.
3. The user signs in and grants access on Apple's site.
4. The connector binds the resulting grant to that user's MCP authorization.
5. Each tool call accesses only the mailbox associated with the authenticated user.

This is the intended behavior, not functionality provided by the current release.
Users do not configure personal mailbox credentials in the service deployment.
An ordinary identity login is not sufficient to grant access to an iCloud mailbox.

## Evidence and unresolved dependency

Apple's [third-party app support article](https://support.apple.com/en-us/121539)
confirms account authorization for supported apps accessing iCloud Mail, Calendar,
and Contacts. It explains user consent and revocation, but does not provide a
developer registration process, mail scopes, or token-to-mail protocol details.

[Sign in with Apple](https://developer.apple.com/documentation/signinwithapple)
documents signing users into an application. That documentation does not establish
that its identity tokens authorize iCloud Mail access.

The separately documented [Account & Organizational Data Sharing authorization
endpoint](https://developer.apple.com/documentation/accountorganizationaldatasharing/request-an-authorization)
lists `edu.users.read` and `edu.classes.read` as valid scopes. Those are not mail
permissions. Its similar name is not proof that it exposes the authorization
described in the iCloud support article.

The sources reviewed do not establish a usable iCloud Mail integration contract
for this project. This is an unresolved dependency, not a claim that Apple never
supports mail authorization for third-party apps.

Before implementing the Apple adapter, obtain authoritative information covering:

- How an independent connector registers for iCloud Mail authorization, including
  any eligibility or approval requirements.
- The authorization and token endpoints, supported grants, mail permissions,
  redirect URI requirements, and client authentication method.
- How a grant identifies the mailbox and authenticates the supported mail protocol
  or API, including aliases and custom domains.
- Token expiration, refresh, revocation, and disconnection behavior.

Do not implement guessed endpoints or scopes, use another application's client
identity, or replace this flow with a form collecting Apple passwords. An Apple
Developer inquiry may be needed if no public integration documentation is available.

## Required changes after the Apple contract is verified

- Separate service configuration from per-user mailbox grants. Deployment settings
  may contain application registration and encryption secrets, not a preselected
  user's mailbox password.
- Bind MCP codes, access tokens, refresh tokens, and consent to a stable user and
  connection identity. An MCP client ID identifies an application, not a person.
- Resolve the mailbox from the authenticated connection for every tool call. Never
  select another user's grant from a caller-supplied email address or mailbox ID.
- Keep the Apple and MCP token lifecycles separate. Protect any retained upstream
  tokens, exclude them from logs and tool responses, and document their storage.
- Isolate mailbox state, draft retry identifiers, and rate limits across users.
- Disconnect and revoke only the intended user's connection, including when
  multiple people use the same MCP client application.
- Test account isolation, callback binding, consent, refresh, revocation, and real
  mailbox access before enabling a shared deployment.

OAuth grants are credentials too. Automatic authorization avoids manual password
configuration; it does not mean a functioning service has no access capability.
The token storage design remains to be determined from Apple's actual contract.

## Existing implementation

`Config` contains one email address and one app-specific password. `build_server`
creates one `Mailbox`; the OAuth provider assigns `subject='owner'`. Revocation
currently removes tokens by MCP client ID. These assumptions are appropriate only
for the existing single-owner prototype and must not be reused as user isolation.

The current `render.yaml`, Docker setup, and local setup remain prototype deployment
options. They are not the public service described above. The repository's existing
tests do not demonstrate multi-user isolation or Apple-native mail authorization.
