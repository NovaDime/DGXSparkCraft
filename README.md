# SparkCraft 1.0 · 助力开发你想要的世界

用 NVIDIA DGX Spark 打造游戏 UGC 多智能体“AI 圆桌”协作系统。

**NVIDIA DGX Spark 黑客松 · NVIDIA Developer社区说的都队**

面向 Minecraft 中国版开发。六位圆桌成员分别负责主持、策划、数值、技术可行性、音效与独立审查；程序虾仁负责代码制作。会议形成方案后，由人审核任务单，再自动下发编码和音效任务，检查后生成附加包 ZIP。当前默认目标为中国版基岩 1.24，最终兼容性仍须目标游戏验收。


## DGX Spark 快速开始

Ubuntu / Linux ARM64，Python 3.12+；模型部署需要已配置 NVIDIA 容器运行环境的 Docker。首次需要网络下载 Python 依赖、Node、OpenClaw、模型权重及容器，不是包含模型的离线整机镜像。

```bash
chmod +x *.sh
./一键部署.sh --dry-run   # 查看部署动作，不修改环境
./一键部署.sh            # 准备依赖，复用或部署 Nemotron，启动并打开工作台
```

已有 `.venv`、OpenClaw 和本机模型的用户直接运行：

```bash
./启动.sh               # 启动或复用服务，自动打开默认浏览器 /studio
./后台监控.sh           # 后台健康记录
./结束.sh               # 只结束本项目 Studio、Gateway 与监控
./安装桌面快捷方式.sh    # 为当前位置生成可双击的启动、部署图标
```

Linux 文件管理器可能将 `.sh` 双击解释为打开文本。安装桌面快捷方式后，双击 **SparkCraft 创作工作室**；若桌面提示“允许启动”，按系统提示启用。搬动目录后重新生成快捷方式。无图形界面时启动脚本会打印访问地址。

新版入口：[http://127.0.0.1:8765/studio](http://127.0.0.1:8765/studio)。详细前提、固定版本与下载说明见 [DGX Spark 部署](docs/DGX-Spark部署.md)。部署检测到已有模型/GPU任务时不会将其停止或替换。默认模型端口 8000、项目 Gateway 19789、Studio 8765，均仅本机访问。

## 使用流程

1. **代码库与知识 → 我的世界**：官方 API 与开发指南是默认前置资料，不需要选择代码库才进入 Agent 上下文。卡片区分基础规则、参考快照与官网正文；可刷新资料或上传离线文档。其他游戏显示“未来更新”。
2. 可选上传代码库 ZIP 或导入本机目录，检索引用片段；原目录不被覆盖。文档识别模型支持本地模型与自配云端 API。
3. **协作圆桌**：填写议题、约束及讨论上限，点像素虾查看/更换模型。讨论最多 1000 轮且受 1M 累计 token 预算保护；未解决分歧不会伪装成共识。
4. 形成共识后整理任务单，由用户审核并批准，再执行程序和音效制作。StepAudio 默认 `stepaudio-3-gen-preview`，使用自己的 StepFun API Key。
5. 在工作台或 VS Code 审阅代码、检查证据、下载包。需要目标游戏实测的结果不会标记为已验证。

任务、会议记录可移入回收站并恢复；运行中先停止。会议记录可折叠。经验沉淀采用索引与人工采纳，**不会训练或更改模型权重**。

## 官方基础资料

- [中国版官方 API](https://mc.163.com/dev/apidocs.html)
- [中国版官方开发指南](https://mc.163.com/dev/guide.html)

内置 `knowledge/minecraft/` 为本项目整理的导航和核验规则。启动首次尝试同步，正文仅存本机 `data/official-knowledge/`。官网不可访问时，API 可回退到固定提交的 MCNeteaseDevs 文档参考快照，界面明确标记。指南全文未获取时保持“正文尚未索引”。Agent 必须核对具体接口与目标 SDK，不能从首页链接推断接口签名。

## 目录与发布

```text
roundtable/          后端与新版工作台界面
skills/              圆桌、编码、音效与知识技能
knowledge/minecraft/ 默认官方资料导航与开发核验规则
scripts/             启动、部署、桌面入口、发布打包工具
docs/                使用、架构与验证说明
examples/            可导入的最小示例
tests/               自动测试
compat/windows/      历史 Windows 入口，仅兼容保留
```

`.env`、`data/`、`.venv/`、`.runtime/`、历史网页存档及动态桌面入口不进入发布包。API 密钥保存在 `data/private/`；会议、用户代码与模型配置都属于本机数据。

```bash
.venv/bin/python -m unittest discover -s tests -q
.venv/bin/python scripts/package_release.py --output ../V1.0便携版
```

便携版可移动源码，在目标机按上述步骤准备依赖；不携带作者的模型权重、凭证或用户数据。发布脚本拒绝覆盖已有目录。

[人工审核与交付](docs/approved-delivery.md) · [资料功能与限制](docs/document-library-beta.md) · [开发说明](docs/minecraft-development.md)

