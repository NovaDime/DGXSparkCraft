---
name: spark-connect
description: 准备单台 DGX Spark 的模型、OpenClaw 与 Studio 连接，排查部署和启动问题。
---

# Spark 连接与部署准备

此技能面向部署操作者，不新增圆桌角色。连接前读取 [连接前提](references/connect.md)，配置前读取 [配置准备](references/prepare.md)，部署完成读取 [交付检查](references/acceptance.md)。

优先复用已就绪服务。核对模型列表、OpenClaw 认证与 Studio 地址，不把端口连通当成推理已验证。默认端口为 8000、19789、8765，实际值以运行配置为准。不要终止其他项目进程，不打印密钥。

入口为 Linux 启动与部署脚本。报告应区分依赖安装、模型加载、接口就绪与实际调用，不编造进度或结果。模型路由与素材能力以 README 为准，不套用旧版固定五角色或固定云端策划约束。
