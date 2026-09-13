# 本地验收记录

## 会议轮询同毫秒更新修复 · 2026-09-13

在 `fix/meeting-poll-version-check` 分支执行 `python -B -m unittest discover -s tests`：65 项通过；`node --check roundtable/static/app.js` 通过。新增测试证明多条事件即使拥有相同毫秒时间戳，事件 ID 仍按序递增。页面现在同时比较时间、事件数量、发言数量和状态，不再只依赖毫秒时间戳判断是否需要刷新。未进行新版浏览器手动验收。

## Agent 工具默认拒绝分支验证 · 2026-09-13

在 `feat/agent-tools-denied-by-default` 分支执行 `python -B -m unittest discover -s tests`：64 项通过。导出测试确认五个角色的工具策略均为 `profile: minimal` 且 `deny: ["*"]`；原有模型路由和敏感凭证不导出检查仍通过。

这是部署片段的本地结构检查；没有在目标 OpenClaw 版本或 Spark 上验证实际工具拒绝效果，也没有执行 Agent 侧数值脚本。

## 严格双模型路由分支验证 · 2026-09-13

在 `feat/strict-hybrid-model-routing` 分支执行 `python -B -m unittest discover -s tests`：64 项通过。导出测试确认策划固定云端模型引用、其余四个角色固定本地引用，主模型无回退且 `utilityModel` 使用同一路由；缺失、格式错误或同 provider 的模型引用会在写入部署包前被拒绝。

这是本地配置生成和校验结果，不是 OpenClaw 目标版本配置验收。云端 API、Spark 本地模型服务、网络隔离及真实角色调用尚未联调。

## 五角色、3 至 4 轮分支验证 · 2026-09-13

在 `feat/five-agent-three-four-rounds` 分支执行 `python -B -m unittest discover -s tests -v`：63 项通过。覆盖新会议固定五角色、至少三轮后才能收敛、第三轮新增问题时进入第四轮、第四轮仍有分歧时待复核，以及 API 和页面限制。

执行 `python -B scripts/verify_local.py`：7 项本地规则模拟检查通过，完成 3 轮、16 次发言；五角色顺序、分歧登记与关闭、Skill 指纹均通过。可审阅文件仍位于 `artifacts/local-verification/`。

执行 `node --check roundtable/static/app.js`：语法检查通过。本次未进行新版页面浏览器验收、真实 OpenClaw 调用或 Spark 联调；上述结果不代表模型效果和设备性能。

## 先前版本的历史验收 · 2026-09-13

以下记录来自改动前版本 0.1.0，当时允许关闭第二位程序员，会议也可在第一或第二轮结束；不作为当前分支的验收结论。验收对象是从零实现的 Python 圆桌、专业 Skills 和网页；实际 OpenClaw、Spark 模型和网易游戏环境尚未联调。

### 自动化结果

`python -m unittest discover -s tests -v`：60 项通过（加入 Windows 运行管理脚本后的完整回归）。完整输出位于 `artifacts/test-output.txt`。

覆盖逐轮固定方案评审、角色顺序、分歧关闭权限、修订后重新评审、停止与排队、中断恢复、API、OpenClaw HTTP 请求与响应验证、凭证脱敏、角色工作区导出，以及数值 Skill 的计算边界。OpenClaw 测试使用模拟 HTTP 响应，不是远端实际调用。

Windows 管理脚本新增 5 项实际进程测试：重复启动不重复创建服务；正常关闭保存活动会议并能重启；强制结束释放服务与启动进程、重启恢复中断记录；拒绝接管占用端口及无效进程身份；从项目外通过 PowerShell 转发参数。使用独立临时数据库和空闲端口。

另外已实际执行根目录三个 CMD 入口：启动（`--no-browser`）、状态查询（`--json`）、关闭，再次启动。全部返回成功，正式数据目录原有 3 条模拟会议保留。详细功能与操作见 [项目说明与使用手册](../项目说明与使用手册.md)。

`python scripts/verify_local.py`：6 项流程检查通过，完成 2 轮、11 次模拟发言。可审阅文件：

- `artifacts/local-verification/summary.json`：检查摘要。
- `artifacts/local-verification/meeting.md`：方案与完整会议记录。
- `artifacts/local-verification/meeting.json`：结构化原始记录。

`node --check roundtable/static/app.js`：语法检查通过。

### 浏览器验收

在本地页面 `http://127.0.0.1:8765` 操作验证：

| 场景 | 实际结果 |
| --- | --- |
| 五角色完整会议 | 两轮后模拟收敛，11 次发言，4 条分歧复核关闭 |
| 四角色、一轮上限 | 5 次发言后显示“仍需评审”，保留 3 条未解决分歧 |
| 手动停止 | 显示“已停止”，停止前意见和未解决分歧保留 |
| 历史会议切换与刷新 | 恢复对应会议、角色、方案与发言记录 |
| 方案与总结 | 能切换阅读并触发 Markdown 下载；JSON 导出接口由 API 测试验证 |
| 数值 Skill | 显示专业指令、计算工具参考说明和内容指纹 |
| 运行配置 | 模拟模式连接检查明确表示未连接 OpenClaw 或 Spark |
| 手机宽度 | 在 390 × 844 视口测试，页面无横向溢出，已恢复默认视口 |

验收中修复了长议题标题过长、文字偏小、切换会议时旧操作按钮仍显示，以及静态资源缓存延迟更新的问题。浏览器检查未记录控制台错误或警告。

## 待连接设备后完成

实际模型能否遵守角色协议、专业质疑是否有效、OpenClaw 是否执行计算工具、Spark 资源占用与耗时，以及 ModSDK 和游戏内行为，均待实测。

`build/openclaw-preview/` 是已生成的本地角色部署预览，包含 5 个独立工作区、Skills、配置片段和文件指纹，未安装到任何设备。远端目录仍为文档占位路径 `/home/your-user/ugc-roundtable`，取得 Spark 的实际账户和目录后重新导出。
