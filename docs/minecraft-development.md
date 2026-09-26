# Minecraft 中国版开发工作流

DGXSparkCraft 的开发工作台把圆桌结论、上传仓库和编码产物连起来：导入代码 → 检索相关实现 → 编码 Agent 生成变更 → 可信脚本静态检查 → 独立 Agent 审查 → 最多两次修复 → 在 VS Code 审阅 → 采纳有证据的项目经验。

范围只包括开发过程。联机服务、地图制作、测试账号、上架和收益均不属于本版功能。静态检查保留运行时、SDK 与引擎未验证的边界，不要求接入游戏账号才能使用开发工作台。

## 在开发工作台中使用

1. 选择本地目录导入或上传代码 ZIP。目录路径指圆桌服务所在机器；从另一台电脑访问网页时，使用上传。导入结果会显示实际读取文件和跳过项，原目录不会被编码任务直接覆写。
2. 选择代码库，先用功能名、类名或 API 名检索，确认文件路径和行号确实对应目标实现。更新本地源目录后重新索引；ZIP 内容改变时重新上传形成新快照。
3. 输入明确的开发任务，例如“沿用该仓库结构，新增可重复调用的冷却判定纯逻辑，游戏 API 适配单独列出”。也可把已形成共识的圆桌方案关联到任务。
4. 显式选择 `python2` 或 `python3`，并在任务中写出已知的 ModSDK/引擎版本。`python2` 是保守开发选项；实际游戏运行时仍须查目标工具资料。不要把 Python 3 的圆桌后端版本当成模组版本。
5. 查看阶段日志、代码差异、假设、API 依据、静态检查和独立审查。修复预算为 0–2 次；达到预算仍未通过会保留待复核状态与产物。
6. 在服务所在机器通过“在 VS Code 打开”审阅独立工作区；其他电脑可下载产物 ZIP 后用 VS Code 打开。开发任务不会自动把变更合并回用户源目录。
7. 查看学习候选，填写实际验证依据后再采纳。候选不自动成为事实，也不会自动训练模型权重。

模拟模式只验证流水线和界面，生成固定样例，不实现任意需求。真实模式下必须查看实际模型调用记录；网关错误不能转换成看似成功的模拟结果。

## 编码与学习能力

| Skill | 输入与结果 |
|---|---|
| [modsdk-coding](../skills/modsdk-coding/SKILL.md) | 任务、完整可修改源文件、带出处的检索材料 → 完整变更文件、假设、接口依据与静态审查修复 |
| [repository-learning](../skills/repository-learning/SKILL.md) | 代码库快照、开发结果、用户提供的验证依据 → 可追踪的项目经验；仅采纳条目进入后续上下文 |
| 既有圆桌 Skills | 保留玩法、数值、技术可行性和独立逻辑评审；开发工作台在其后接入交付环节 |

编码 Agent 与审查 Agent 分工独立，但如果共用同一底层模型，不能据此声称模型误差相互独立。自动审查只能提供额外检查意见。

## API 依据与运行时边界

用户提供的 [官方 API 入口](https://mc.163.com/dev/apidocs.html) 和 [官方开发指南](https://mc.163.com/dev/guide.html) 是核验首选。2026-09-25 本次环境无法读取其正文，当前补充依据来自 MCNeteaseDevs 技术手册固定快照，已读取的条目与具体端别见 [API 证据记录](../skills/modsdk-coding/references/api-evidence.md)。不能以此声称目标项目适配最新 ModSDK。

已核验的快照条目包括两端各自的 `RegisterSystem`、服务端 `GetServerSystemCls`、客户端 `GetClientSystemCls` 和 `ListenForEvent`/`UnListenForEvent`。它们足以约束系统注册与事件订阅的基本结构，不能证明任何物品、UI、持久化或自定义事件字段。未查证的接口会作为缺口保留，不用看似合理的名称替代文档。

主程序可在 DGX Spark 的 Python 3 环境中检索和产出 Python 2 源文件；目标引擎语法、可导入模块与 API 可用性是另一层约束。VS Code 的补全、主机 AST 解析与真实游戏运行分别记录。

## 独立使用可信校验器

在项目根目录执行，参数指向待审阅产物目录：

```bash
python3 skills/modsdk-coding/scripts/validate_modsdk.py /absolute/path/to/workspace --runtime python2
```

校验器不执行产物代码。它检查 JSON 解析、重复键和非有限值、Python 3 主机语法、部分 Python 2 明确不兼容语法、编码声明及可确定的端别导入混用。对 Python 2 始终保留未执行目标解释器检查的警告。退出码 0 仅表示这些检查未发现错误，不能作为模组可运行证明。[完整范围与限制](../skills/modsdk-coding/references/validation.md)。

可信校验器的行为测试：

```bash
python3 skills/modsdk-coding/evals/test_validation.py -v
```

它验证非法 JSON、Python 2/3 混用、端别导入、符号链接和文件大小边界，同时确认项目代码从未被执行。面向模型的前向评估题位于两个 Skill 的 `evals/evals.json`，题目不是已经完成的模型评测成绩。

## 开发 API

以下为本地服务接口；默认服务地址与启动配置见项目 README。

| 接口 | 功能 |
|---|---|
| `POST /api/repositories/import` | JSON `path` 和可选 `name`，导入服务机器上的显式目录 |
| `POST /api/repositories/upload?name=...` | 原始 ZIP 请求体，上传上限 20 MiB |
| `GET /api/repositories/{id}/search?q=...` | 检索带路径、行号和来源的材料 |
| `POST /api/repositories/{id}/reindex` | 刷新已导入的代码索引 |
| `GET /api/repositories/{id}/feedback` | 查看代码库学习条目 |
| `POST /api/development/jobs` | `task`、可选 `repository_id`/`meeting_id`、`runtime`、`max_repairs` |
| `GET /api/development/jobs/{id}` | 查看开发状态、变更、检查、来源与审查意见 |
| `GET /api/development/jobs/{id}/download` | 下载可在 VS Code 审阅的产物 |

上传仓库是检索资料，不会自动执行其中的安装脚本、Git hooks 或测试。生成代码也不会因出现在模型响应中而获得终端权限。
