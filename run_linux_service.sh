#!/usr/bin/env bash
set -uo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ -x "${APP_DIR}/venv/bin/python" ]]; then
  PYTHON_EXE="${APP_DIR}/venv/bin/python"
elif [[ -x "${APP_DIR}/.venv/bin/python" ]]; then
  PYTHON_EXE="${APP_DIR}/.venv/bin/python"
else
  PYTHON_EXE="$(command -v python3)"
fi

cd "${APP_DIR}" || exit 1
mkdir -p logs

LOG_FILE="logs/saldo-ao-vivo-$(date +%Y%m%d-%H%M%S).log"

echo "Inicio: $(date -Is)" | tee -a "${LOG_FILE}"
echo "Python: ${PYTHON_EXE}" | tee -a "${LOG_FILE}"

"${PYTHON_EXE}" "${APP_DIR}/main.py" 2>&1 | tee -a "${LOG_FILE}"
STATUS=${PIPESTATUS[0]}

echo "Fim: $(date -Is) status=${STATUS}" | tee -a "${LOG_FILE}"
exit "${STATUS}"
