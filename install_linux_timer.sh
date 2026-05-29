#!/usr/bin/env bash
set -euo pipefail

APP_NAME="saldo-ao-vivo"
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_FILE="/etc/systemd/system/${APP_NAME}.service"
TIMER_FILE="/etc/systemd/system/${APP_NAME}.timer"
RUN_USER="${SUDO_USER:-$USER}"

if [[ -x "${APP_DIR}/venv/bin/python" ]]; then
  PYTHON_EXE="${APP_DIR}/venv/bin/python"
elif [[ -x "${APP_DIR}/.venv/bin/python" ]]; then
  PYTHON_EXE="${APP_DIR}/.venv/bin/python"
else
  PYTHON_EXE="$(command -v python3)"
fi

if [[ ! -f "${APP_DIR}/main.py" ]]; then
  echo "ERRO: main.py nao encontrado em ${APP_DIR}"
  exit 1
fi

sudo tee "${SERVICE_FILE}" >/dev/null <<EOF
[Unit]
Description=Saldo ao Vivo
Wants=network-online.target
After=network-online.target

[Service]
Type=oneshot
User=${RUN_USER}
WorkingDirectory="${APP_DIR}"
Environment=PYTHONUNBUFFERED=1
ExecStart="${PYTHON_EXE}" "${APP_DIR}/main.py"
EOF

sudo tee "${TIMER_FILE}" >/dev/null <<EOF
[Unit]
Description=Executa Saldo ao Vivo de hora em hora

[Timer]
OnCalendar=hourly
Persistent=true
Unit=${APP_NAME}.service

[Install]
WantedBy=timers.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now "${APP_NAME}.timer"

echo "Agendamento instalado com sucesso."
echo "Servico: ${SERVICE_FILE}"
echo "Timer: ${TIMER_FILE}"
echo
echo "Proximas execucoes:"
systemctl list-timers "${APP_NAME}.timer" --no-pager
echo
echo "Para ver logs:"
echo "journalctl -u ${APP_NAME}.service -f"
