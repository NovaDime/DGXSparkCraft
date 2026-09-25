# 暂存配置与部署预检

在项目根目录操作，完整步骤见 `docs/spark-connection-requirements.md` 的「配置生成与 dry-run」。保留现有运行配置，在忽略目录 `artifacts/spark/` 准备 `generated.env`，不直接改活动 `.env`。

确认以下暂存值：运行模式为 `openclaw`；Gateway 为实际地址；五个 Agent ID 唯一且与目标配置一致；请求与上下文预算适合已选模型。Gateway Token 留空，真实运行凭证由目标环境注入；操作系统环境变量会覆盖暂存值。

用实际云端、本地 provider/model 和目标工作区目录替换示例参数，先运行：

```text
python scripts/export_openclaw.py --env-file artifacts/spark/generated.env --target-root /home/spark/ugc-roundtable --planner-model cloud-provider/planner-model-id --local-model spark-local/local-model-id --output build/spark-candidate --dry-run
```

`--dry-run` 不写输出文件、不访问网络、不调用真实模型；只验证本地输入并输出脱敏计划。核对输出的模式、角色路由、Gateway、无回退和工具默认拒绝。若出现 `simulation`，先排查环境覆盖和暂存配置；不能作为真实部署配置接受。

通过后去掉 `--dry-run`，以同一组参数生成候选包。输出目录须为空。保存 `deployment-plan.json`、`openclaw.fragment.json`、角色工作区、Skill Card、INSTALL 和文件清单。

将片段合入目标版本的专用暂存配置，另配 provider、认证、监听及执行隔离；使用该版本真实可用的配置校验方式，不猜 CLI。已获准部署时按授权范围激活并保留回滚配置。只有参考材料而无实际设备信息时，到本地候选包为止。

本项目没有 VSS/Compose 部署，不能伪造 `resolved.yml` 或把截图中的辅助脚本名说成本项目现有命令。我们的解析产物是 JSON；它不包含 OpenClaw provider 的完整配置。
