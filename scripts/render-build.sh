#!/usr/bin/env bash
set -euo pipefail
python -m pip install -r requirements.lock
python -m pip install --no-deps .
python -m pytest -q
