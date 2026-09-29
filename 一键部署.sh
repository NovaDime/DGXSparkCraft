#!/usr/bin/env bash
set -uo pipefail
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
python3 "$project_dir/scripts/deploy_spark.py" "$@"
result=$?
if (( result != 0 )) && [[ -t 0 ]]; then read -r -p '部署未完成，请阅读上方错误。按回车关闭…' _; fi
exit "$result"
