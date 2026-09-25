# 接入 Spark

当前阶段可完成本地流程与 HTTP 协议验证。Spark 尚未取得访问条件，本文是待执行的连接步骤，不代表已经部署、测过内存或验证过模型质量。

新增连接信息、配置暂存、dry-run、Skill Card、签名与验收要求见 [Spark 连接与 Skill 交付要求](spark-connection-requirements.md)。部署辅助入口见 [spark-connect](../skills/spark-connect/SKILL.md)。不接入 Blockbench 或其他美术工具，也不将截图中的双机、VSS 端口和模型当作本项目配置。

## 连接方式

最终只使用一台 DGX Spark：Python 页面、圆桌调度器、OpenClaw Gateway 和本地模型服务都在同一设备上。Gateway 与本地模型接口只绑定本机或受控内部网络；策划的模型 provider 单独访问云端 API。Windows 阶段只用于本地模拟和开发测试，不作为最终运行节点。不要把 Gateway Token 或云端 API 密钥写入网址、仓库或浏览器页面。

## 准备角色工作区

1. 核实 Spark 上实际的 OpenClaw 版本、云端模型引用、本地模型服务、模型名称及量化方式。取得设备访问条件后再部署，不预先套用博客的模型和性能数字。
2. 先在 `artifacts/spark/generated.env` 准备非秘密暂存配置，使用 `--env-file artifacts/spark/generated.env --dry-run` 预检（具体命令见上述要求）。本地 dry-run 不写文件、不连接 Spark；之后在开发机生成专用工作区，目标路径和模型引用替换为实际值：

   ```powershell
   python scripts/export_openclaw.py --env-file artifacts/spark/generated.env --target-root /home/your-user/ugc-roundtable --planner-model cloud-provider/planner-model-id --local-model spark-local/local-model-id
   ```

3. 将生成目录放到 Spark 专用目录，在目标 OpenClaw 的专用配置中合并 `openclaw.fragment.json`。该片段包含五个角色的工作区、Skill 可见性、固定主模型、同路由 `utilityModel`、空回退列表、全部 Agent 工具拒绝策略和 Responses 开关；不包含模型权重、provider 端点、认证或执行沙箱设置。已有同名 Agent 时先修改本地 Agent ID 再重新导出，避免混入其他项目会话。
4. 依据目标 OpenClaw 版本校验配置。当前导出器使用 `agents.entries`；旧版若使用其他配置结构，按对应版本官方文档迁移。不要用片段覆盖完整配置。
5. 分别配置云端和 Spark 本地 provider 的真实端点、认证与网络策略；确认策划只会访问指定云端 API，其余四个角色不能经 provider 回退访问外网。保留 Gateway 回环监听和认证。每个工作区只安装该角色的 Skill；本版导出片段默认拒绝所有 Agent 工具，数值脚本不在 Agent 中执行。若需开放脚本或文件读取，先在目标版本与 OpenShell 沙箱中单独验证权限，再明确修改策略。Skill 的文字说明和可见性都不能替代执行沙箱。

模型引用不同只能防止继承同一默认模型，**不能证明** provider 端点确实分别位于云端和本机。策划收到的议题、约束和当前方案会离开 Spark；发送真实资料前必须确认云端服务的数据保留政策和脱敏边界。

OpenClaw 的 `POST /v1/responses` 默认关闭，需要 `gateway.http.endpoints.responses.enabled=true`；它与 Gateway 共用端口。调用通过 `model: openclaw/<agentId>` 选择角色。[HTTP 接口说明](https://docs.openclaw.ai/gateway/openresponses-http-api)

导出片段使用官方 [工具策略](https://docs.openclaw.ai/gateway/config-tools/tool-policy) 中的 per-agent `tools.profile` 和通配 `deny`。这仅是预期配置；目标版本仍须运行配置校验、逐角色拒绝测试和沙箱检查。

## 本地配置

先在忽略目录中由 `.env.example` 生成 `generated.env`，完成本地与目标配置校验后，再在 Spark 圆桌项目目录激活为 `.env`。使用以下实际配置；真实凭证在目标环境单独注入，暂存文件保留 Token 空值。Shell 环境变量优先于 `.env`；修改后重启圆桌服务。

```dotenv
ROUNDTABLE_PROVIDER=openclaw
OPENCLAW_BASE_URL=http://127.0.0.1:18789
# 暂存文件留空；真实凭证由 Spark 运行环境注入。
OPENCLAW_TOKEN=
OPENCLAW_MODEL=openclaw
OPENCLAW_AGENT_HOST=host
OPENCLAW_AGENT_PLANNER=planner
OPENCLAW_AGENT_BALANCE=balance
OPENCLAW_AGENT_ENGINEER=engineer
OPENCLAW_AGENT_REVIEWER=reviewer
ROUNDTABLE_REQUEST_TIMEOUT=180
ROUNDTABLE_MAX_CONTEXT_CHARS=24000
ROUNDTABLE_MAX_OUTPUT_TOKENS=4096
```

五个 Agent ID 必须与 Spark 上的 OpenClaw 配置对应且彼此不同。`OPENCLAW_MODEL` 是配置展示标签，实际请求使用各角色 `openclaw/<agentId>`；各角色的后端模型由导出片段中的 `agents.entries.<agentId>.model` 指定。云端 API 密钥、两个 provider 的端点和本地模型权重在 OpenClaw 侧单独配置。字符预算不是 token 数，也不代表可用上下文窗口。

## 首次联调顺序

- 先使用页面连接检查，确认 `/v1/models` 可返回。此步骤只说明 Gateway 连通。
- 逐个角色完成一次真实调用，确认返回协议、角色职责和 Skill 内容；再跑一个完整议题，检查是否有实际质疑、修订和问题复核。
- 先保持串行调用与默认轮数；记录真实模型名、量化、上下文设置、每次调用耗时和未报告的指标。只有服务返回的 token 数才能写为实际用量；没有值时保留未知。
- 在 Spark 端单独记录内存、设备负载和模型服务日志。页面显示的调用耗时包含 Gateway 与策划云端网络时间，不能直接当作本地模型吞吐率。
- 检查实际调用日志：策划走云端，主管、数值和两名程序角色走本地；任一 provider 不可用时必须显式失败，不得静默跨路由回退。

认证失败检查专用 Token；404 检查 Responses 开关与路径；超时先查远端模型日志；结构化输出失败检查实际模型回复。失败会议保留记录并明确停止原因，修复环境后新建一场会议。SDK 与游戏行为另在 Windows 开发工作台实测，Spark 的 Linux 环境不被当作网易客户端测试环境。
