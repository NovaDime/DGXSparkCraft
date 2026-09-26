# 目标版本与 API 依据

查阅日期：2026-09-25。目标项目的 ModSDK 版本、基岩引擎版本和游戏内 Python 运行时尚未由用户提供。

## 官方入口与本次可读证据

- [官方 API 文档入口](https://mc.163.com/dev/apidocs.html)
- [官方开发指南入口](https://mc.163.com/dev/guide.html)

本次联网无法读取以上入口正文，因此不声称已核验其最新版本。可读补充材料为 [MCNeteaseDevs 维护的技术手册仓库](https://github.com/MCNeteaseDevs/mc-netease-sdk)，固定快照 `4a9b3f90ccb7ab0c631815d004f07a9e4f64c950`。这是版本有边界的参考证据，不能替代目标开发工作台随附文档。

| 已读取的条目 | 声明的接口与边界 |
|---|---|
| [System.md](https://github.com/MCNeteaseDevs/mc-netease-sdk/blob/4a9b3f90ccb7ab0c631815d004f07a9e4f64c950/1-ModAPI/接口/通用/System.md) | `mod.server.extraServerApi.RegisterSystem(nameSpace, systemName, clsPath)` 与 `mod.client.extraClientApi.RegisterSystem(...)` 分别注册对应端系统，类路径从脚本第一层起；返回对应系统实例。不能互换模块。 |
| 同上 | `GetServerSystemCls()` 位于 `mod.server.extraServerApi`、只用于服务端；`GetClientSystemCls()` 位于 `mod.client.extraClientApi`、只用于客户端。各自无参数、返回系统基类。 |
| [事件.md](https://github.com/MCNeteaseDevs/mc-netease-sdk/blob/4a9b3f90ccb7ab0c631815d004f07a9e4f64c950/1-ModAPI/接口/通用/事件.md) | `BaseSystem.ListenForEvent(namespace, systemName, eventName, instance, func, priority=0)` 两端均有；监听引擎事件时 namespace/systemName 来自相应获取方法。具体回调字段仍须读取该事件条目，不能从名称推断。 |
| 同上 | `UnListenForEvent` 与监听对应，参数包括相同 namespace、systemName、eventName、instance、func 和 priority。文档并不由此证明任意热重载流程正确。 |

以上仅覆盖注册和事件订阅。物品、方块、UI、组件工厂、状态保存等实现必须另查具体接口，不能把这张表当作完整白名单。引用正文摘要而非复制整份第三方手册。

## 运行时

手册示例含 Python 2 风格写法；[MCNeteaseDevs 文档辅助项目](https://github.com/MCNeteaseDevs/modsdk_mcp_server)当前 README 声明其资料面向 ModSDK 3.9 / BE 1.21.120，并包含 Python 2.7 约束。这是该项目快照的声明，不是本用户项目版本确认。

选择 `python2` 时避免 f-string、类型注解、`async`/`await`、`yield from`、关键字专用参数等 Python 3 语法；包含中文的源码应声明编码。也不要把 `u"text"` 一概判为 Python 2 不支持，它本身是 Python 2 语法；特定引擎字符串限制须另有目标版本证据。

选择 `python3` 只表示任务要求 Python 3 语法，不证明网易引擎支持它。编辑器补全库、圆桌后端和文档工具的 Python 版本均不能作为游戏运行时证据。

## 每条证据的最小记录

记录准确符号、模块/类、端别、参数/事件字段、返回值/限制、目标版本或快照、页面/文件与段落、读取日期。已有用户代码证明的是项目使用过该模式；只有目标运行日志能证明该场景实际成功。遇到冲突时保持未知，不把模型共识当成 API 来源。
