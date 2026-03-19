#!/usr/bin/env bash
set -euo pipefail

if [[ "$#" -eq 0 ]]; then
  exec streamlit run app.py --server.address=0.0.0.0 --server.port=8501
else
  exec python main.py "$@"
fi