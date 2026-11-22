#!/bin/bash
# Invoked by launchd (see com.market.daily.plist). Logs go to backend/data/logs/.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p data/logs
exec "$HOME/.local/bin/uv" run python -m market.jobs.daily >> "data/logs/daily-$(date +%Y-%m).log" 2>&1
