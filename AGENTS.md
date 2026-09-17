# Repository instructions

## Documentation language

- Always write and update repository documentation in English, including README
  files, setup and deployment guides, and agent instructions.
- Write code comments, docstrings, and user-facing project text in English.
- Preserve identifiers, commands, configuration keys, proper names, and intentional
  non-English test fixtures when translating.
- This repository language rule does not change the language of conversations with
  the user.

## Public connector design

- The product target is a reusable connector with per-user Apple authorization
  initiated from the MCP client. Do not design the public service around one
  operator's mailbox or require users to configure mailbox passwords in deployment
  variables or server files.
- The current implementation is a single-account prototype. Keep documentation
  explicit about that limitation until per-user authorization and isolation work.
- Treat MCP authorization and Apple's mailbox authorization as separate layers.
  Do not assume Sign in with Apple grants access to mail, invent Apple mail scopes,
  or reuse another application's client registration.
- Read `docs/authentication.md` before changing authentication, account storage,
  mailbox routing, or deployment defaults. Preserve the prototype while the Apple
  integration prerequisites remain unresolved; do not silently substitute a
  password collection form for Apple authorization.

## Commit messages

- All commit messages must follow [Conventional Commits](https://www.conventionalcommits.org/).
- Use a type, an optional scope, and a concise description, for example: `docs(agents): require conventional commits`.
- Mark breaking changes with `!` before the colon or a `BREAKING CHANGE:` footer, as specified by the standard.
