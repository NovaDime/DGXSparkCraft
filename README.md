# Minecraft UGC · AI 圆桌

面向网易《我的世界》中国版基岩 ModSDK 的本地多角色设计评审系统。
按照两篇项目博客的同一套圆桌思路，从空项目重新实现；未使用旧项目源码。

主管 → 策划 → 数值 → 程序可行性 → 程序逻辑审查 → 主管，围绕分歧进行多轮讨论，最终导出方案和会议记录。
固定 5 个角色，没有美术 Agent；每场会议至少评审 3 轮，最多 4 轮。助手虾的信息收集模块留在后续。

## 当前可用范围

- Python 圆桌调度、角色技能、逐轮方案、分歧台账、SQLite 持久化、网页查看与 Markdown / JSON 导出。
- 全局单任务推理队列、手动停止、超时与轮次上限、服务中断记录恢复。
- 新会议只能选择 3 或 4 轮上限；第 3 轮前不会提前判定收敛。
- 规则模拟与 OpenClaw 两种后端。默认是**规则模拟**，用于验证流程，不是 AI 推理。
- OpenClaw HTTP 适配器、角色工作区导出工具和未来 Spark 接入说明；实际 Spark 尚未联调。
- 每轮专家评审同一版方案。分歧由提出者复核关闭；主持修改过的方案需要重新评审。

本系统交付设计评审建议，不自动生成完整模组。没有把静态检查、模型自报或模拟数据标成游戏验收。

## 本地启动

详细功能、技术实现、完整目录及文件放置说明见 [项目说明与使用手册](项目说明与使用手册.md)。

Windows 日常使用可以直接双击项目根目录的 `启动圆桌.cmd`、`彻底关闭圆桌.cmd`、`查看日志和状态.cmd`。启动脚本会在后台运行服务，日志查看脚本持续显示状态变化和新日志；关闭脚本保留数据库与日志。首次运行仍需准备下面的 Python 依赖。

需要 Python 3.11 或以上，主程序与游戏内 ModSDK 的 Python 环境分开。

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m roundtable
```

打开 <http://127.0.0.1:8765>。默认无需模型、密钥或联网。页面资源均在项目内，不加载外部 CDN。
如果当前 Python 已有依赖，直接运行 `python -m roundtable`。

Linux / Spark 上使用 `.venv/bin/python`，其余命令相同。启动时使用单 worker；重复服务会被数据目录锁拒绝。
需要更换端口时运行 `python -m roundtable --port 8766`。

## 本地验证

```powershell
python -m unittest discover -s tests -v
python scripts/verify_local.py
```

测试包含固定方案评审、角色顺序、分歧关闭权限、假共识阻止、重新评审、取消与排队、中断恢复、HTTP 合约、响应验证和凭证脱敏。
第二条命令生成 `artifacts/local-verification/` 下的模拟会议记录和检查摘要。它不会连接 Spark。
已执行的自动化与浏览器验收见 [本地验收记录](docs/local-validation.md)。

## 接入 OpenClaw / Spark

复制 `.env.example` 为 `.env`，按实际服务填写配置；环境变量优先于 `.env`。不要把 `.env` 提交或放入演示材料。

| 配置 | 作用 |
| --- | --- |
| `ROUNDTABLE_PROVIDER` | `simulation`（默认）或 `openclaw` |
| `OPENCLAW_BASE_URL` | OpenClaw Gateway 地址，默认 `http://127.0.0.1:18789` |
| `OPENCLAW_TOKEN` | Gateway 认证凭证，只由 Python 服务使用 |
| `OPENCLAW_AGENT_*` | 五个专业角色对应的 OpenClaw Agent ID |
| `ROUNDTABLE_REQUEST_TIMEOUT` | 单角色调用超时，默认 180 秒 |
| `ROUNDTABLE_MAX_CONTEXT_CHARS` | 请求上下文字符预算，默认 24000；这不是 token 数 |
| `ROUNDTABLE_MAX_OUTPUT_TOKENS` | 单角色输出 token 预算，默认 4096；网关尽力限制，不完整回复会拒绝采用 |
| `ROUNDTABLE_DATA_DIR` | 会议数据库目录，默认 `data/` |

模型后端在 OpenClaw 中配置。此项目的 `OPENCLAW_MODEL=openclaw` 表示 Gateway 路由入口，不是 Spark 上的模型权重名称。
真实连接失败会停止并保留会议，**不会自动回退模拟**。
连通性检查仅验证 Gateway 的模型列表接口；五个角色和 Skills 仍需分别运行确认。

先生成可审阅的角色部署包（路径改成你们 Spark 的实际目录）：

```powershell
python scripts/export_openclaw.py --target-root /home/your-user/ugc-roundtable
```

生成 `build/openclaw/`：五个角色工作区、Skills、文件指纹和 `openclaw.fragment.json`。导出工具不会操作远程机器、安装框架或覆盖已有配置。
将它部署到目标目录后，在专用 OpenClaw 配置中合并片段、配置本地模型与工具权限，再接通本地应用。
当前片段按 OpenClaw 官方 `agents.entries` 格式生成，目标版本仍需配置校验。具体见 [Spark 接入说明](docs/spark-connection.md)。

## 项目结构

```text
roundtable/          Python 引擎、模型接口、存储、API 与轻量网页
skills/              五个角色的专业 Skills、参考资料和数值工具
examples/            三个可评审议题
scripts/             本地验证、OpenClaw 工作区导出
tests/               自动化回归测试
docs/                架构、Spark 接入和比赛演示说明
web/                 原始网页存档（保留不变）
```

每次发言保存其本地 Skill 内容指纹。`skill_ids` 是模型自报引用，不能单凭该字段认定执行了外部工具。
OpenClaw Agent 的工作区与执行权限在目标服务中配置；Skill 文本本身不是权限隔离。

## 开发依据与验收边界

- [NVIDIA AI 圆桌博客](https://developer.nvidia.cn/blog/spark-ugc-ai-roundtable/)：多专业角色轮流评审、由主管组织再讨论。
- [OpenClaw Skills](https://docs.openclaw.ai/tools/skills)：`SKILL.md`、角色工作区与技能可见性。
- [OpenClaw OpenResponses](https://docs.openclaw.ai/gateway/openresponses-http-api)：通过 `/v1/responses` 调用真实 Agent。
- [网易开发者 ModSDK 资料](https://github.com/MCNeteaseDevs/modsdk_mcp_server)：游戏脚本版本按实际 SDK 核对；不能用主程序 Python 3 的检查代替游戏引擎测试。

当前本地测试不提供真实模型完成率、Spark 内存/性能或游戏兼容性证明。接入 Spark 后按 [演示与验收说明](docs/competition-demo.md) 记录真实结果。
