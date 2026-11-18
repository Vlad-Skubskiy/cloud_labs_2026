#!/usr/bin/env bash
# Запуск навантажувального тесту однією командою: ./loadtest/run.sh
# URL береться з terraform output (або з env URL=...), фази задаються StagesShape у locustfile.py.
set -euo pipefail
cd "$(dirname "$0")/.."
URL="${URL:-$(terraform -chdir=terraform output -raw app_url)}"
mkdir -p loadtest/results
exec locust -f loadtest/locustfile.py --headless --host "$URL" \
  --csv loadtest/results/run --html loadtest/results/report.html "$@"
