# Spark 连接与 Skill 交付要求

更新日期：2026-09-25。依据用户提供的「VSS 部署 Skill」和「Skill Card」两张截图，为本项目新增连接与交付要求；截图是设计参考，不是本项目已完成验收的证明。

## 范围与截图映射

最终运行节点仍为一台 DGX Spark，运行网页服务、Python 调度器、OpenClaw Gateway 和本地模型。策划只走云端 API；主管、数值、程序可行性和程序逻辑审查共用本地模型服务。固定五个角色，每场完成至少 3 轮、最多 4 轮。

不接入 Blockbench，不增加美术 Agent、建模、贴图、动画或 VS Code 控制功能。新增的 `spark-connect` 是运维辅助 Skill，不参与圆桌发言，也不自动安装到五个角色工作区。

| 截图内容 | 本项目采用方式 |
| --- | --- |
| SKILL.md 做路由，细节进入 references | `skills/spark-connect/SKILL.md` 分别指向连接、配置准备和验收资料 |
| copy -> generated.env -> dry-run -> resolved.yml | 保留暂存与预检顺序；本项目没有 Compose 部署文件，以 `deployment-plan.json` 和 `openclaw.fragment.json` 作为本地解析产物，不虚构 resolved.yml |
| 已验证的辅助脚本 | 复用导出器，增加无写入的 `--dry-run` 和暂存配置 `--env-file`；工具返回本地校验与真机检查各自的状态 |
| evals/evals.json + BENCHMARK.md | 提供可读的验收场景与记录模板；场景清单不是自动执行器，未运行项保留 `not_run` |
| 签名 + Skill Card | 为五个角色和运维 Skill 提供机器可读卡片；发布前签名、验签及人工接受分别留证 |
| 两台 Spark、sshpass、30081 端口及示例模型 | 仅为 VSS 演示参数，不构成本项目依赖；不新增第二台 Spark，不照搬模型名或端口 |

## 连接前必须取得的信息

缺失项记录为待填写，不从截图猜测地址、账号、模型或密码。

| 编号 | 必填信息 | 验收依据 |
| --- | --- | --- |
| SP-01 | Spark 主机名/IP、SSH 端口、专用账号、SSH host key 指纹、认证方式 | 授权操作者能连接指定机器；核对主机身份，记录不含密钥的连接结果 |
| SP-02 | 项目代码目录、Agent 工作区目录、数据与日志目录、目录所有者 | 均为该项目的独立绝对路径，具备需要的读写权限，不覆盖其他服务 |
| SP-03 | 系统与架构、Python/OpenClaw/推理服务版本、安装方式 | 对照实机记录；依赖须适配 Spark 的实际系统与架构，不能复制 Windows 虚拟环境 |
| SP-04 | 本地模型精确 ID/版本、量化、上下文、服务地址、认证方式 | 实际加载日志及单次调用；四个本地角色使用指定服务，不配置云端回退 |
| SP-05 | 策划云端 provider/model、API 地址、凭证注入方式、使用地域 | 实际调用及路由记录；确认允许发送的议题资料、服务地域与费用边界 |
| SP-06 | Gateway 地址、Responses 开关、五个唯一 Agent ID、认证 | 模型列表连通后，还须逐个完成真实角色调用 |
| SP-07 | 网页/Gateway/模型服务端口、浏览器访问方式 | 实际监听与连通记录；区分直接在 Spark 操作与开发机通过 SSH 隧道访问 |
| SP-08 | 部署与回滚责任人、代码提交、Skill/模型来源和许可 | Skill Card 及交付记录；未明确的责任人、许可和地域不得标为已接受 |

最终单机部署时，网页与 Gateway 默认走 Spark 回环地址，端口以实际配置为准。开发机经 SSH 访问只是管理通道，不成为第二个推理节点。优先使用现有 SSH 密钥或交互式认证；截图中的 `sshpass` 不作为必装项。密码、私钥和 API Token 不写进卡片、命令参数、模型上下文或公开日志；SSH 用户名可以作为已确认的连接参数。

## 配置生成与 dry-run

1. 保留当前部署版本及配置。把 `.env.example` 复制到 Git 忽略目录 `artifacts/spark/generated.env`，只修改这份暂存文件；设定 `ROUNDTABLE_PROVIDER=openclaw`、实际 Gateway 地址和 Agent ID。这里的 Token 留空，凭证在目标运行环境中单独注入。
2. 在 OpenClaw 的专用暂存配置中分别准备云端、本地 provider。记录端点与模型引用，凭证用目标版本支持的密钥引用或受控配置。角色导出器不生成 provider 或系统级权限配置。
3. 使用实际 provider/model 与目标工作区目录运行以下命令。示例值仅说明格式，部署前必须替换：

   ```powershell
   python scripts/export_openclaw.py --env-file artifacts/spark/generated.env --target-root /home/spark/ugc-roundtable --planner-model cloud-provider/planner-model-id --local-model spark-local/local-model-id --output build/spark-candidate --dry-run
   ```

   此命令检查本地角色、Skill、目录参数、模型引用与配置约束，输出脱敏部署计划；不创建输出目录，不执行 SSH、不访问 API、不安装模型。环境变量优先于暂存文件，应核对输出计划中的实际模式、Gateway 地址和预算。`local_config=passed` 不能证明目标端点可用。
4. 本地预检通过后，使用同一组参数去掉 `--dry-run`，在空目录中生成候选包。保留 `deployment-plan.json`、`openclaw.fragment.json`、角色工作区、Skill Card 和 `manifest.json`。已有输出目录非空时导出器拒绝覆盖。
5. 将候选包交给已授权操作者，在目标 OpenClaw 的暂存配置中合并片段，并使用目标版本支持的配置校验方式验证。具体命令需以实际安装版本为准，本项目不预设一个未经验证的 OpenClaw CLI 命令。
6. 核对本地模型路由、工具拒绝策略、监听地址和凭证来源后，才在目标机器激活配置、启动单 worker 服务并执行真实验收。保留原配置以便失败时恢复，已有会议数据库和日志不删除。

当前导出器生成的 `deployment-plan.json` 是脱敏的本地有效配置摘要，不是 OpenClaw 完整最终配置，也不证明模型实际位于本地或云端。它明确记录 `network_contacted=false`、`installed=false`、真机检查 `not_run` 和 `signature=unsigned`。

## Skill Card 与信任记录

每个 Skill 随附 `SKILL_CARD.json`，字段涵盖截图中的用途、负责人、许可与地域、前提依赖、风险与缓解、参考资料/版本/伦理说明。卡片是机器可读的项目约定格式，不声称兼容某个尚未确定的官方校验器。

| 字段 | 填写要求 |
| --- | --- |
| `description` / `use_cases` | 明确服务对象、任务与不承担的工作 |
| `owner` | 项目归属、实际责任人、联系信息和确认状态；未确认时使用 null/pending |
| `license` / `deployment_geography` | 使用与分发条款、适用地域、云端数据去向；未声明许可不等于可自由再分发 |
| `requirements` / `dependencies` | 模型路由、运行环境、外部服务、工具权限和凭证引用名称；不包含凭证值 |
| `risks_and_mitigations` | 每项风险对应操作限制或验证证据，尤其是云端资料发送和未实测结论 |
| `references` / `version` / `ethical_considerations` | 来源、版本、限制及未完成验证 |
| `trust` | 扫描、效果评估、签名、接受和重复检查分别记录状态及证据路径 |

截图区分扫描、效果、签名、接受与重复检查，本项目同样分别记录。截图中的产品/层级名称作为背景信息，不强制安装未确认的评估或签名产品。

- `manifest.json` 是 SHA-256 文件清单，用于比较内容；它没有签名者身份，不能当数字签名。
- 发布负责人确定签名工具、身份和信任根后，对最终包或最终 manifest 签名；接收方同时验证签名和全部文件散列，保存结果。签名后修改文件必须重新生成清单并签名。
- 当前未配置签名基础设施，状态为 `unsigned`。卡片中的 `pending` 也不能替代真实人员的接受记录。
- 仓库当前没有声明项目分发许可；责任人须确认项目、模型、依赖及第三方 Skill 的许可与适用地域。这里不会自动指定开源许可证。
- 本地开发与未签名试运行可以明确记录为开发状态；不能作为完成了正式签名与接受的交付。

## 分层验收与交付物

验收场景见 [evals.json](../skills/spark-connect/evals/evals.json)，记录表见 [BENCHMARK.md](../skills/spark-connect/BENCHMARK.md)。部署人员将实测副本和日志保存在受控的验收目录，再填写报告中的路径与结果。

| 编号 | 验收层 | 必须保留的证据 |
| --- | --- | --- |
| AC-01 | SSH 与主机身份 | 指定主机连接结果、系统/架构信息、路径与版本；不含认证秘密 |
| AC-02 | 配置 dry-run | 暂存配置来源、代码版本、模型引用、部署计划及目标 OpenClaw 配置校验结果 |
| AC-03 | Gateway | `/v1/models` 结果与时间；单独标注尚不证明角色推理成功 |
| AC-04 | 五角色真实调用 | 各角色输入、结构化输出、Skill 指纹及实际 provider/model 路由日志 |
| AC-05 | 3/4 轮会议 | 三轮与四轮上限场景；第三轮前不结束，第四轮未收敛标记待复核；不要求模型必然同意 |
| AC-06 | 隔离与秘密保护 | 工具拒绝测试、云端/本地无回退、示例假 Token 不出现在输出；真实密钥不进入评测样本 |
| AC-07 | 失败与恢复 | 超时、鉴权失败、结构错误和中断记录；不得回退模拟或未经确认自动续跑 |
| AC-08 | 资源与效果 | 实际模型、量化、上下文、串行配置、调用耗时、内存/设备采样、已报告的 token 用量和专业复核意见 |
| AC-09 | 交付完整性 | Skill Card、文件清单、扫描/效果记录、签名与验签结果、责任人的接受记录；未做项明确列出 |

仅静态校验、模拟会议、接口连通、模型自报、截图中案例的性能数字均不能替代 Spark 实测。当前尚无真实设备访问条件，AC-01 和 AC-03 至 AC-09 的真机/正式交付部分均待执行。
