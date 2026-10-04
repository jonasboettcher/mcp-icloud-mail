#!/usr/bin/env bash
set -euo pipefail
python3 -m venv .lexware-venv
.lexware-venv/bin/pip install -r requirements.lock
if [ ! -d .lexware-runtime/.git ]; then
  git clone https://github.com/marselsel/Lexware-MCP-Server.git .lexware-runtime
fi
git -C .lexware-runtime fetch origin 8da792d08146665036943a9ee7d1b7f444225939
git -C .lexware-runtime reset --hard 8da792d08146665036943a9ee7d1b7f444225939
(cd .lexware-runtime && npm ci && npm test)
.lexware-venv/bin/python -m lexware_gateway.patch_backend .lexware-runtime
(cd .lexware-runtime && npm run build)
.lexware-venv/bin/python -m pytest -q lexware_gateway/tests
