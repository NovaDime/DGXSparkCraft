#!/usr/bin/env bash
set -uo pipefail
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [[ ! -f "$project_dir/scripts/linux_studio.py" ]]; then
  printf '缺少 scripts/linux_studio.py。请完整解压 SparkCraft 文件夹，不要单独下载或移动启动.sh。\n'
  if [[ -t 0 ]]; then read -r -p '按回车关闭窗口…' _; fi
  exit 1
fi
python3 "$project_dir/scripts/linux_studio.py" start-background "$@"
result=$?
if (( result == 0 )); then
  python3 "$project_dir/scripts/linux_studio.py" follow-startup
  result=$?
fi
if (( result != 0 )); then
  printf '\n启动失败（退出码 %s）。日志在 %s/data/runtime/\n' "$result" "$project_dir"
  if [[ -t 0 ]]; then read -r -p '按回车关闭窗口…' _; fi
fi
if (( result == 0 )) && [[ -t 0 ]]; then
  read -r -p '工作台已就绪。按回车关闭此窗口（服务继续运行）…' _
fi
exit "$result"
