# 接入 Spark

当前阶段可完成本地流程与 HTTP 协议验证。Spark 尚未取得访问条件，本文是待执行的连接步骤，不代表已经部署、测过内存或验证过模型质量。

## 连接方式

建议 Python 页面与调度器先留在 Windows，Spark 运行 OpenClaw 和本地模型。公网 IP 用于建立 SSH 连接，Gateway 保持监听 Spark 本机回环地址。这样本地程序继续访问 `http://127.0.0.1:18789`。这是 OpenClaw 官方提供的远程访问方式之一。[远程连接说明](https://docs.openclaw.ai/gateway/remote)

拿到实际的 SSH 用户名、IP 与端口后，在 Windows 终端运行并保持该终端连接：

```powershell
ssh -N -L 127.0.0.1:18789:127.0.0.1:18789 -p <SSH端口> <用户名>@<Spark公网IP>
```

占位符替换为实际值。首次连接核对主机身份；若本地 18789 已占用，可将 `-L` 中第一个端口改为 18790，并将本地 `OPENCLAW_BASE_URL` 改为 `http://127.0.0.1:18790`。不要把 Gateway Token 写在网址或浏览器页面里。

## 准备角色工作区

1. 核实 Spark 上实际的 OpenClaw 版本、模型服务、模型名称及量化方式。确认 SSH 可用后再部署，不预先套用博客的模型和性能数字。
2. 在本地导出专用工作区，目标路径替换为 Spark 用户实际路径：

   ```powershell
   python scripts/export_openclaw.py --target-root /home/your-user/ugc-roundtable
   ```

3. 将生成目录放到指定远端目录，在目标 OpenClaw 的专用配置中合并 `openclaw.fragment.json`。该片段只包含角色工作区、Skill 可见性和 Responses 开关；不包含模型权重、认证或工具权限。已有同名 Agent 时先修改本地 Agent ID 再重新导出，避免混入其他项目会话。
4. 依据目标 OpenClaw 版本校验配置。当前导出器使用 `agents.entries`；旧版若使用其他配置结构，按对应版本官方文档迁移。不要用片段覆盖完整配置。
5. 保留 Gateway 回环监听，配置认证与各角色工具权限。每个工作区只安装该角色的 Skill；需要计算或读取参考资料时确认 Python 与文件读取工具实际可用。Skill 的文字说明和可见性都不能替代执行沙箱。

OpenClaw 的 `POST /v1/responses` 默认关闭，需要 `gateway.http.endpoints.responses.enabled=true`；它与 Gateway 共用端口。调用通过 `model: openclaw/<agentId>` 选择角色。[HTTP 接口说明](https://docs.openclaw.ai/gateway/openresponses-http-api)

## 本地配置

复制 `.env.example` 为 `.env`，使用以下实际配置。Shell 环境变量优先于 `.env`；修改后重启本地服务。

```dotenv
ROUNDTABLE_PROVIDER=openclaw
OPENCLAW_BASE_URL=http://127.0.0.1:18789
OPENCLAW_TOKEN=填写专用Gateway凭证
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

五个 Agent ID 必须与远端配置对应且彼此不同。`OPENCLAW_MODEL` 是配置展示标签，实际请求使用各角色 `openclaw/<agentId>`；本地推理模型权重在 OpenClaw 配置中选择。字符预算不是 token 数，也不代表可用上下文窗口。

## 首次联调顺序

- 先使用页面连接检查，确认 `/v1/models` 可返回。此步骤只说明 Gateway 连通。
- 逐个角色完成一次真实调用，确认返回协议、角色职责和 Skill 内容；再跑一个完整议题，检查是否有实际质疑、修订和问题复核。
- 先保持串行调用与默认轮数；记录真实模型名、量化、上下文设置、每次调用耗时和未报告的指标。只有服务返回的 token 数才能写为实际用量；没有值时保留未知。
- 在 Spark 端单独记录内存、设备负载和模型服务日志。本地页面显示的调用耗时包含网络与 Gateway 时间，不能直接当作模型吞吐率。
- 对 5 角色与关闭第二名程序员的 4 角色运行进行对比。结合问题发现质量和实际资源决定配置；不把角色数量当作同时加载的模型数量。

认证失败检查专用 Token；404 检查 Responses 开关与路径；超时先查远端模型日志；结构化输出失败检查实际模型回复。失败会议保留记录并明确停止原因，修复环境后新建一场会议。SDK 与游戏行为另在 Windows 开发工作台实测，Spark 的 Linux 环境不被当作网易客户端测试环境。
