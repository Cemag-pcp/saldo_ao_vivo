#!/usr/bin/env bash
set -euo pipefail

APP_NAME="saldo-ao-vivo"
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_FILE="/etc/systemd/system/${APP_NAME}.service"
TIMER_FILE="/etc/systemd/system/${APP_NAME}.timer"
RUN_USER="${SUDO_USER:-$USER}"
RUN_HOME="$(getent passwd "${RUN_USER}" | cut -d: -f6)"
VENV_DIR="${APP_DIR}/venv"
PYTHON_EXE="${VENV_DIR}/bin/python"

if [[ ! -f "${APP_DIR}/main.py" ]]; then
  echo "ERRO: main.py nao encontrado em ${APP_DIR}"
  exit 1
fi

mkdir -p "${APP_DIR}/logs"
chmod +x "${APP_DIR}/run_linux_service.sh"

if [[ ! -x "${PYTHON_EXE}" ]]; then
  echo "Ambiente virtual ausente ou quebrado. Recriando venv..."
  rm -rf "${VENV_DIR}"
  python3 -m venv "${VENV_DIR}"
fi

if ! "${PYTHON_EXE}" -c "import sys; print(sys.executable)" >/dev/null 2>&1; then
  echo "Python do venv nao executa corretamente. Recriando venv..."
  rm -rf "${VENV_DIR}"
  python3 -m venv "${VENV_DIR}"
fi

echo "Instalando/atualizando dependencias no venv..."
"${PYTHON_EXE}" -m pip install --upgrade pip
"${PYTHON_EXE}" -m pip install -r "${APP_DIR}/requirements.txt"
"${PYTHON_EXE}" -m playwright install chromium
"${PYTHON_EXE}" -c "from playwright.sync_api import sync_playwright; print('playwright_ok')"

sudo tee "${SERVICE_FILE}" >/dev/null <<EOF
[Unit]
Description=Saldo ao Vivo
Wants=network-online.target
After=network-online.target

[Service]
Type=oneshot
User=${RUN_USER}
Environment="HOME=${RUN_HOME}"
Environment="APP_DIR=${APP_DIR}"
Environment="PYTHON_EXE=${PYTHON_EXE}"
Environment=PYTHONUNBUFFERED=1
WorkingDirectory=${APP_DIR}
ExecStart=/usr/bin/env bash "${APP_DIR}/run_linux_service.sh"
EOF

sudo tee "${TIMER_FILE}" >/dev/null <<EOF
[Unit]
Description=Executa Saldo ao Vivo de hora em hora das 07:00 as 19:00

[Timer]
OnCalendar=*-*-* 07..19:00:00
Persistent=true
Unit=${APP_NAME}.service

[Install]
WantedBy=timers.target
EOF

sudo systemctl daemon-reload
sudo systemctl reset-failed "${APP_NAME}.service" "${APP_NAME}.timer" >/dev/null 2>&1 || true
sudo systemctl enable "${APP_NAME}.timer"

if ! sudo systemctl start "${APP_NAME}.timer"; then
  echo
  echo "ERRO: nao foi possivel iniciar o timer."
  echo
  echo "Status do timer:"
  sudo systemctl status "${APP_NAME}.timer" --no-pager || true
  echo
  echo "Status do servico:"
  sudo systemctl status "${APP_NAME}.service" --no-pager || true
  echo
  echo "Ultimos logs do servico:"
  sudo journalctl -u "${APP_NAME}.service" -n 80 --no-pager || true
  exit 1
fi

if ! systemctl is-active --quiet "${APP_NAME}.timer"; then
  echo
  echo "ERRO: o timer foi criado, mas nao esta ativo."
  echo
  sudo systemctl status "${APP_NAME}.timer" --no-pager || true
  echo
  sudo journalctl -u "${APP_NAME}.service" -n 80 --no-pager || true
  exit 1
fi

echo "Agendamento instalado com sucesso."
echo "Servico: ${SERVICE_FILE}"
echo "Timer: ${TIMER_FILE}"
echo
echo "Proximas execucoes:"
systemctl list-timers --all "${APP_NAME}.timer" --no-pager
echo
echo "Para ver logs:"
echo "journalctl -u ${APP_NAME}.service -f"
echo
echo "Logs em arquivo:"
echo "${APP_DIR}/logs/"
