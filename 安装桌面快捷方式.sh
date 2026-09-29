#!/usr/bin/env bash
set -uo pipefail
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
python3 "$project_dir/scripts/install_desktop.py"
result=$?
if [[ -t 0 ]]; then read -r -p '已处理；如桌面提示不受信任，请右键选择“允许启动”。按回车关闭…' _; fi
exit "$result"
