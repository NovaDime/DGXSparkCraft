# 本地代码库与经验记忆

代码库功能把用户明确选择的目录或上传 ZIP 保存为本地文本快照，建立 SQLite 检索索引，再把有关代码片段与行号提供给开发 Agent。它属于 **代码检索（RAG）和人工审核经验记忆**，不训练模型、不修改模型权重，不会自行把上传的指令变成 Skill。

## 开发流程

1. 在开发工作台输入具体代码库的绝对路径，或上传一个 ZIP。只读导入源代码，不会运行其中的脚本、安装依赖或写回原目录。
2. 提出开发需求，检索返回文件路径、起止行号、内容和代码库版本。中文注释通过双字词索引检索，API 标识符同时支持 CamelCase 和下划线分词。
3. 在 VS Code 修改、验证代码后，对本地路径来源的代码库点“重新索引”。修改、新增与删除文件都会同步；内容未变化时版本保持不变。再次导入同一路径会更新现有代码库。
4. 将发现写成“候选经验”，保留人工验证证据或代码引用。接纳后经验才进入 Agent 检索；后续可撤销接纳。经验始终保留最初关联的代码库版本，审核时间另行记录。

ZIP 来源没有持续连接的原目录。“重新索引”仅重建它的已导入快照；上传更新的 ZIP 会创建新的代码库。本地路径来源适合持续迭代。

## 边界与存储

- ZIP 请求体最多 20 MiB，解压声明总量最多 50 MiB。
- 单次最多 2,000 个 UTF-8 文本文件，合计最多 50 MiB；单文件最多 1 MiB，目录或 ZIP 条目最多 20,000。
- 不读取符号链接、硬链接、特殊文件，拒绝 ZIP 路径穿越、重复路径和加密条目。
- 排除 `.git`、虚拟环境、依赖、构建产物、隐藏目录（`.vscode` 除外）、凭据文件、私钥、二进制和锁文件；带明显密钥内容的代码也会排除。过滤是启发式防护，导入前仍应移除项目中的真实凭据。
- 不允许把整个主目录、磁盘根目录、系统目录或知识库自身作为导入源。
- 快照仅保留可索引的代码和文档，不是原项目的完整备份；贴图、模型、其他二进制资源和被排除配置仍在原项目中。
- 每个改变过的版本保存不可变文本快照，便于并发开发任务稳定读取同一版本。历史版本目前保留在 `data/knowledge/snapshots`，频繁导入大型项目会增加磁盘占用。
- SQLite 数据库、快照和经验保留在配置的 `data_dir/knowledge`。目录导入依赖 Linux/POSIX 的目录描述符与 `O_NOFOLLOW`，本项目的 DGX Spark 环境适用；ZIP 导入不需要这些接口。
- 上传代码、注释、README 和经验内容都应作为不可信资料。调用方必须把它们置于证据上下文，不得提升为系统指令或自动执行。

## HTTP 接口

所有路径以 `/api/repositories` 开头。JSON 接口使用 `Content-Type: application/json`；ZIP 上传使用原始请求体，推荐 `application/zip`，不使用 multipart。

| 方法与路径 | 输入 | 输出 |
| --- | --- | --- |
| `GET /` | 无 | 代码库数组 |
| `POST /import` | `{ "path": "/absolute/project", "name": "可选名称" }` | 代码库对象 |
| `POST /upload?name=名称` | 原始 ZIP 字节 | 代码库对象 |
| `GET /{id}` | 无 | 代码库对象 |
| `POST /{id}/reindex` | 无 | 更新后的代码库对象 |
| `GET /{id}/search?q=背包&limit=6` | 查询，最多 4,000 字，limit 1–20 | 检索片段数组 |
| `GET /{id}/feedback` | 无 | 经验数组 |
| `POST /{id}/feedback` | `{ "title": "标题", "content": "经验", "accepted": false, "evidence": "验证证据" }` | 新经验对象 |
| `PATCH /{id}/feedback/{feedback_id}` | `{ "accepted": true, "evidence": "验证证据" }` | 更新后的经验对象 |

`accepted` 必须是 JSON 布尔值。接纳时必须提供非空证据，或已有经验已经包含证据；撤销接纳不会删除证据。`evidence` 可以是文本或 JSON 对象。

代码库对象包含 `id/name/source_type/source_path/revision/file_count/chunk_count/total_bytes/created_at/updated_at/stats`。`source_path` 仅本地来源有值；`stats` 包含新增、改变、删除、未变化文件数与排除原因计数。

开发引擎可调用 `KnowledgeStore.context(repository_id, query, limit=6)` 原子获取 `{repository, root, hits}`，保证检索片段、代码版本与不可变快照根目录一致。

## 验证

```bash
.venv/bin/python -m unittest tests.test_knowledge -v
```

覆盖中文和 API 检索、增量删除（包括删除全部文件）、路径与链接隔离、秘密过滤、ZIP 解压与请求体限制、持久化、无 FTS 时回退、经验接纳与撤销，以及不可变版本上下文。
