#!/usr/bin/env bash
set -uo pipefail
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
python3 "$project_dir/scripts/linux_studio.py" start "$@"
result=$?
if (( result != 0 )); then
  printf '\n启动失败（退出码 %s）。日志在 %s/data/runtime/\n' "$result" "$project_dir"
  if [[ -t 0 ]]; then read -r -p '按回车关闭窗口…' _; fi
fi
exit "$result"
