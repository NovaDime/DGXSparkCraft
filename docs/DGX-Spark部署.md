# DGX Spark 本地部署与双击启动

在目标 DGX Spark 上解压完整项目，首次打开终端进入项目目录：

```bash
bash 一键部署.sh --dry-run   # 只展示步骤，零写入/零安装/零服务启动
bash 一键部署.sh             # 联网安装依赖、复用或创建模型，然后打开工作室
```

安装目标：项目私有 `.runtime/node`（Node 26.7.0 ARM64）、`.runtime/openclaw`（OpenClaw 2026.9.4）和 `.venv`（requirements.txt 固定版本）。不更改全局 npm、用户 `~/.openclaw` 或系统服务。Node 从 nodejs.org 下载并校验官方 SHA256。现有项目私有版本不符会退出，不自动升级。没有必要重新部署时，直接执行 `bash 启动.sh`。

## 桌面入口

部署会根据**当前解压位置**生成“SparkCraft 创作工作室”及“一键部署” `.desktop`，分别放在项目根目录、应用菜单、已有的桌面目录。首次可能需要右键“允许启动”；这是 GNOME 的信任机制，脚本会尝试设置信任标记，但文件系统与桌面实现可能拒绝它。入口 `Terminal=true`，错误时终端保留等待回车。`.sh` 在有些文件管理器中会直接用编辑器打开，应使用生成的 `.desktop`。

也可单独运行：

```bash
bash 安装桌面快捷方式.sh
```

项目搬迁后再执行一次该命令，刷新快捷方式路径；生成的 `.desktop` 不应加入发布包。启动脚本自身通过脚本位置定位项目，不包含本机绝对路径。搬迁后，专用 Gateway 配置中由项目生成的工作区路径会自动修正，凭证和模型选择保持不变。跨机器移动只打包源文件与必要数据，重新部署运行时；Python venv 不能当作跨机器便携依赖。

启动成功、或者项目已经运行时，都会调用系统默认浏览器打开 `http://127.0.0.1:8765/studio`。无图形桌面时仅输出地址。可用 `bash 启动.sh --no-browser` 禁止打开，浏览器错误日志位于 `data/runtime/browser.log`。

## 模型复用与安全边界

脚本先读取 `127.0.0.1:8000/v1/models`；匹配 `nemotron-3.5-lightning` 或完整 NVIDIA 模型名时直接复用，不重启容器。如果端口占用但模型不匹配，或者 NVIDIA GPU 上已有计算进程而没有可复用模型，脚本退出提示检查。部署不执行任何 `docker stop/rm/restart`。

只有模型缺失、端口空闲、GPU 无计算进程时，才用固定 `vllm/vllm-openai:v0.27.1` 创建 `sparkcraft-nemotron-3-5` 容器。仅映射本机回环端口。新容器使用 NVIDIA 模型卡 DGX Spark 的 Marlin、FP8 KV cache、DSpark 配方；权重下载到用户 Hugging Face 缓存，不放入项目与便携包。首次下载/编译最长等待一小时，可用 `--model-timeout 7200` 延长。超时不会停止容器，检查 `docker logs sparkcraft-nemotron-3-5`，模型就绪后重试部署。

OpenClaw 使用项目独立配置 `data/openclaw/openclaw.json` 和 19789 端口；不会接管原来的 18789 Gateway。项目关闭脚本只关闭本项目 Studio/Gateway，不停止复用或新建的模型服务。模型容器不会自动随系统启动；需要运维者明确管理其生命周期。

## 前提与验证范围

需要 Linux ARM64 DGX Spark、Python 3.12+ 与 venv、NVIDIA 驱动、Docker 和 NVIDIA Container Toolkit，以及当前用户可调用 Docker。全新系统可能需要管理员先配置这些系统组件。下载需要访问 nodejs.org、npm、Python 包索引、Docker Hub、Hugging Face；应预留模型主权重与 DSpark 权重、镜像、缓存和运行内存空间，具体占用依下载版本而定。若节点没有 xdg-open/图形桌面，可从有浏览器的客户端通过 SSH 端口转发访问。

本次交付验证了启动和部署分支的单元测试、无副作用 dry-run 和本机模型探测；没有实际下载安装运行时或启动/重启 GPU 服务。因此新机器完整下载与首次模型加载仍需目标设备联网验收。

参考：[NVIDIA 官方模型卡与 DGX Spark 配方](https://huggingface.co/nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-NVFP4)、[OpenClaw 官方安装说明](https://docs.openclaw.ai/install)。版本固定于本项目已使用的组合，升级应单独验证。
