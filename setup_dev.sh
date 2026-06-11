#!/bin/sh
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
git config core.hooksPath .github/hooks
echo "Dev environment ready."
