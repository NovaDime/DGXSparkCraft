# Spark 连接验收记录模板

此文件是空白记录模板，不是实测报告。复制到受控验收目录后填写；未做的项目保持 `not_run`，未知数值保持 null。评测场景定义见 [evals/evals.json](evals/evals.json)。

## 环境

| 字段 | 结果 |
| --- | --- |
| 执行人、日期、代码提交、工作区改动状态 | null |
| Spark 身份、系统、架构 | null |
| Python / OpenClaw / 推理服务版本 | null |
| 本地模型 ID、版本、量化、上下文 | null |
| 云端策划 provider/model、服务地域 | null |
| 五个 Agent ID、文件清单与配置计划路径 | null |
| 并发 / 轮数上限 / 单次请求超时 | null |
| SSH / Gateway / 云端认证 | 仅记录方式或环境变量名称，不填密钥 |

## 执行证据

| 场景 / 层级 | 状态 | 输入与实际结果、证据路径 |
| --- | --- | --- |
| 本地软件测试与 dry-run | not_run | null |
| SSH 主机身份和目录 | not_run | null |
| 目标配置校验 | not_run | null |
| Gateway 连通 | not_run | null |
| 五角色真实调用及路由 | not_run | null |
| 三轮会议 | not_run | null |
| 四轮上限与未收敛 | not_run | null |
| 工具拒绝、无回退、假 Token 脱敏 | not_run | null |
| 超时、鉴权、无效输出与中断恢复 | not_run | null |
| 专业意见实际价值与人工复核 | not_run | null |
| 签名及验签 | unsigned | null |
| 责任人接受 / 许可地域确认 | pending | null |
| 安全扫描 / 效果评估 / 重复检查 | not_run | null |

## 资源与用量

| 指标 | 值 | 来源与采样方式 |
| --- | --- | --- |
| 成功 / 失败角色调用数 | null | null |
| 每角色调用耗时 / 会议总墙钟耗时 | null | null |
| Spark 内存、设备负载和峰值 | null | null |
| 输入 / 输出 token | null | 仅记录服务实际报告值 |
| 云端调用费用 | null | 依据实际账单与使用量 |

设备采样和 API 调用耗时分别留证，不将包含网络等待的耗时当本地 token/s。失败、取消和未收敛的记录同样保留。结论只覆盖已执行的输入与环境，不将本地模拟、文件指纹或截图中的案例结果写为真机证据。
