#!/bin/sh
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
if [ ! -x .venv/bin/python ] || [ ! -x bridge/target/debug/note4-weather-bridge ]; then
  echo '请先运行 sh install.sh'; exit 1
fi
if [ ! -f config.json ]; then echo '请先复制 config.example.json 为 config.json 并填写配置'; exit 1; fi
exec .venv/bin/python app.py --config config.json "$@"
