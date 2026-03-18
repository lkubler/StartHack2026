#!/usr/bin/env bash
set -euo pipefail

if [[ "$#" -eq 0 ]]; then
  exec python client.py demo_capture 10
else
  exec python client.py "$@"
fi