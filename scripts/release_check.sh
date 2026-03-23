#!/bin/sh
set -eu

ROOT_DIR="$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)"

echo "[1/6] Backend tests"
(cd "$ROOT_DIR/backend" && ./venv/bin/python manage.py test apps.k8s_gateway apps.streams apps.iam apps.rbac_bridge apps.clusters apps.audit apps.system_settings)

echo "[2/6] Django system check"
(cd "$ROOT_DIR/backend" && ./venv/bin/python manage.py check)

echo "[3/6] Frontend type check"
(cd "$ROOT_DIR/frontend" && npm run check)

echo "[4/6] Frontend build"
(cd "$ROOT_DIR/frontend" && npm run build)

echo "[5/6] Compose config validation"
if command -v docker >/dev/null 2>&1; then
  (cd "$ROOT_DIR" && docker compose -f docker-compose.prod.yml config >/dev/null)
else
  echo "docker not found, fallback to YAML parse"
  python3 - <<'PY'
from pathlib import Path
import yaml

compose_path = Path("docker-compose.prod.yml")
with compose_path.open("r", encoding="utf-8") as handle:
    payload = yaml.safe_load(handle)

assert isinstance(payload, dict), "compose file must be a mapping"
assert "services" in payload, "compose file missing services"
assert "backend" in payload["services"], "compose file missing backend service"
assert "frontend" in payload["services"], "compose file missing frontend service"
print("compose yaml parsed")
PY
fi

echo "[6/6] Helm chart validation"
if command -v helm >/dev/null 2>&1; then
  (cd "$ROOT_DIR" && helm lint deploy/helm/kuboard >/dev/null)
  (cd "$ROOT_DIR" && helm template kuboard deploy/helm/kuboard >/dev/null)
else
  echo "helm not found, fallback to chart metadata parse"
  python3 - <<'PY'
from pathlib import Path
import yaml

for relative_path in ("deploy/helm/kuboard/Chart.yaml", "deploy/helm/kuboard/values.yaml"):
    chart_path = Path(relative_path)
    with chart_path.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle)
    assert isinstance(payload, dict), f"{relative_path} must be a mapping"
    print(f"{relative_path} parsed")
PY
fi

echo "release checks passed"
