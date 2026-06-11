python -m venv .venv
.venv\Scripts\pip install -r requirements-dev.txt
git config core.hooksPath .github/hooks
Write-Host "Dev environment ready."
