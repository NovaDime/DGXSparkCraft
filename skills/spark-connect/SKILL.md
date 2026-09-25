---
name: spark-connect
description: 为 spark-game 准备单台 DGX Spark 连接、暂存配置、本地 dry-run 和分层验收材料。用于部署与连接排查，不参与五角色圆桌评审，不接入美术工具。
---

# Spark 连接与部署准备

从本项目根目录执行辅助命令。此 Skill 随仓库提供给部署操作者；不会由圆桌引擎注册成新角色，也不自动获得 SSH、安装或启动服务的权限。

## 按请求选择资料

| 请求 | 加载资料 |
| --- | --- |
| 连接 Spark、核对 SSH/模型/Gateway 条件 | [连接前提](references/connect.md) |
| 生成部署包、检查暂存配置、执行 dry-run | [配置准备](references/prepare.md) |
| 真机验收、性能记录、Skill 交付 | [验收记录](references/acceptance.md)、[评测场景](evals/evals.json)、[记录表](BENCHMARK.md) |

保留单台 Spark、五角色、3 至 4 轮、策划云端与其余本地、无回退和默认工具拒绝的边界。模型名、端口与账号采用本项目实际值，不能照搬 VSS 截图。工具脚本复用仓库 `scripts/export_openclaw.py`，本技能不自带另一套部署实现。

报告需区分本地预检、真实连接、角色执行与设备测量。没有设备或凭证时完成本地准备并列出缺项；不编造连接结果、工具执行、签名或接受记录。秘密仅引用名称或注入方式，不打印值。

依赖、责任人与当前信任状态见 [SKILL_CARD.json](SKILL_CARD.json)。
