# Spark 连接

当前操作步骤见 [DGX Spark 部署](DGX-Spark部署.md) 与 [部署说明](部署说明.md)。

SparkCraft 1.2 在单台 DGX Spark 上运行。准备 Linux ARM64、Python 3.12 与 venv、NVIDIA 驱动、Docker 和 NVIDIA Container Toolkit。首次安装需要网络；先运行 `./一键部署.sh --dry-run` 可预览动作。

默认本机模型端口为 8000，项目 OpenClaw 为 19789，Studio 为 8765。启动时检测并复用已就绪服务，不接管其他项目进程。使用 `./启动.sh` 打开系统默认浏览器；使用 `./后台监控.sh` 查看健康状态。

圆桌包含七位成员，代码制作由程序虾仁执行。各角色可配置本地或云端模型，不假定策划必须走云端。美术多模态入口的可用范围见 README。密钥仅保存在本机，不进入源码包。
