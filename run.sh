#!/bin/bash
# Helper script to run the job automation engine with the correct Python from venv
# Ao final de cada execução, exibe o Report de Sniper (últimas 24h + ROI).

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
PYTHON="${SCRIPT_DIR}/venv/bin/python3"

# Executa o pipeline principal
"$PYTHON" main.py "$@"
EXIT_CODE=$?

# Sempre exibe o relatório de performance (Vagas encontradas vs E-mails enviados)
echo ""
"$PYTHON" modules/generate_report.py

exit "$EXIT_CODE"

