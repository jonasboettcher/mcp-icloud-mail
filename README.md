# MCP sources moved

The maintained implementations have moved to the private central repository
[tradmusica/mcps](https://github.com/tradmusica/mcps):

| Component | Maintained source |
| --- | --- |
| iCloud Mail | [servers/icloud-mail](https://github.com/tradmusica/mcps/tree/main/servers/icloud-mail) |
| Lexware Office | [servers/lexware-office](https://github.com/tradmusica/mcps/tree/main/servers/lexware-office) |
| Subke | [servers/subke-mcp](https://github.com/tradmusica/mcps/tree/main/servers/subke-mcp) |

This repository is a migration pointer. Runtime source, tests, dependencies,
connector metadata and deployment configuration are maintained centrally.
The existing Render services retain their endpoints, secrets and persistent
state. Their source repository is now `tradmusica/mcps`.

The four original branches and their complete Git history are also preserved
under `archive/icloud-mail/*` in the central repository. Historical commits here
remain recoverable; this move does not rewrite history or erase provenance.
Do not resume MCP development or deployment from this repository.
