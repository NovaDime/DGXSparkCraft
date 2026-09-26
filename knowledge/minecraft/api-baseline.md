# Minecraft 中国版官方 API 基础资料

主入口：https://mc.163.com/dev/apidocs.html
对象：网易中国版基岩 ModSDK。用户项目目标为中国版基岩 1.24，不能直接据此推断 ModSDK 版本或国际版 min_engine_version。

开发前置规则：
- 编写游戏调用前核对具体接口正文：名称、客户端/服务端、参数、返回值、限制及目标版本。
- API 入口页只用于导航，不能作为所有接口签名都已核验的证据。
- 区分中国版 ModSDK 与国际版 Script API，不按接口名称猜测参数。
- 已知参考：客户端系统基类由客户端模块的 GetClientSystemCls 获取；服务端使用对应服务端系统基类。RegisterSystem 注册系统，事件订阅与取消订阅需匹配。
- 缺少具体页面证据时，先实现可审查的业务逻辑，并记录待核验项，不能虚构 API 或游戏测试结果。

参考资料：
https://github.com/MCNeteaseDevs/mc-netease-sdk/blob/4a9b3f90ccb7ab0c631815d004f07a9e4f64c950/1-ModAPI/接口/通用/System.md
https://github.com/MCNeteaseDevs/mc-netease-sdk/blob/4a9b3f90ccb7ab0c631815d004f07a9e4f64c950/1-ModAPI/接口/通用/事件.md

这是 SparkCraft 整理的开发核验基线，不是官网全文镜像。正文同步成功后可检索具体片段，仍需核对目标 SDK 版本。
