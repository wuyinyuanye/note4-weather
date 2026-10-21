#!/bin/sh
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
for tool in python3 cargo cmake curl; do
  command -v "$tool" >/dev/null 2>&1 || { echo "缺少 $tool，请阅读 README.md 安装依赖"; exit 1; }
done
python3 -c 'import sys; assert sys.version_info >= (3,10), "需要 Python 3.10+"'
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
CMAKE_POLICY_VERSION_MINIMUM=3.5 cargo build --locked --manifest-path bridge/Cargo.toml
if [ ! -e config.json ]; then
  cp config.example.json config.json
  chmod 600 config.json
fi
printf '%s\n' '安装完成。请编辑 config.json，填写自己的设备 IPv4 和设备 ID。' '运行 ./start.sh；控制页预览确认后点击「连接设备」。'
