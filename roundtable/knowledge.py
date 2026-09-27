"""Bounded, local repository snapshots and evidence-backed retrieval.

Imported source is data: this module never imports modules, runs commands or
promotes repository instructions into agent instructions.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import hashlib
import io
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import sqlite3
import stat
import tempfile
from threading import RLock
import uuid
import zipfile

MAX_UPLOAD_BYTES = 20 * 1024 * 1024
MAX_TOTAL_BYTES = 50 * 1024 * 1024
MAX_FILE_BYTES = 1024 * 1024
MAX_FILES = 2000
MAX_ENTRIES = 20000
IGNORED_DIRS = {
    ".git", ".hg", ".svn", "node_modules", "vendor", "build", "dist", "target",
    "venv", ".venv", "env", "__pycache__", ".pytest_cache", ".mypy_cache",
    ".next", ".cache", ".idea", ".ssh", ".aws", ".azure", ".gnupg",
    "secrets", "credentials", "coverage", "logs",
}
EXTENSIONS = {
    ".py", ".pyi", ".json", ".jsonc", ".js", ".jsx", ".ts", ".tsx", ".mjs",
    ".cjs", ".md", ".rst", ".txt", ".yaml", ".yml", ".toml", ".ini", ".cfg",
    ".xml", ".csv", ".mcfunction", ".lang", ".molang", ".mcmeta", ".sh",
    ".bat", ".ps1", ".html", ".css", ".scss", ".c", ".cpp", ".h", ".hpp",
    ".gd", ".gdshader", ".tscn", ".tres", ".luau", ".verse", ".usf", ".ush", ".cs", ".java", ".go", ".rs", ".lua", ".sql", ".properties", ".gradle",
}
SECRET_NAME = re.compile(r"(^|[._-])(secret|secrets|credential|credentials|password|passwords|token|tokens)([._-]|$)", re.I)
SECRET_CONTENT = re.compile(
    r"-----BEGIN (?:[A-Z ]*PRIVATE KEY|OPENSSH PRIVATE KEY)-----"
    r"|\bAKIA[A-Z0-9]{16}\b|\bsk-(?:proj-)?[A-Za-z0-9_-]{24,}"
    r"|(?i:(?:api[_-]?key|access[_-]?token|client[_-]?secret|password|secret[_-]?key)\s*[:=]\s*['\"])([^'\"\n]{8,})['\"]"
)
PLACEHOLDER = re.compile(r"example|placeholder|change.?me|your[_ -]|dummy|test|\$\{|<|not.?a.?real|do.not.expose", re.I)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_name(name: str | None, fallback: str) -> str:
    value = (name or fallback).strip()
    if not value or len(value) > 120 or any(ord(c) < 32 for c in value):
        raise ValueError("代码库名称需为 1–120 个可见字符。")
    return value


def _ignored_path(path: PurePosixPath) -> bool:
    return any(part.lower() in IGNORED_DIRS or (part.startswith(".") and part != ".vscode")
               for part in path.parts[:-1])


def _allowed_file(path: PurePosixPath) -> bool:
    name = path.name.lower()
    if _ignored_path(path) or name.startswith(".") or SECRET_NAME.search(name):
        return False
    if name.startswith(("id_rsa", "id_ed25519", "id_dsa")) or name in {"package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock", "uv.lock"}:
        return False
    return path.suffix.lower() in EXTENSIONS or name in {"dockerfile", "makefile", "license", "readme", "requirements.txt"}


def _decode(data: bytes) -> tuple[str | None, str | None]:
    if b"\x00" in data:
        return None, "binary"
    try:
        content = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return None, "encoding"
    for match in SECRET_CONTENT.finditer(content):
        if not match.lastindex or not PLACEHOLDER.search(match.group(1)):
            return None, "secret_content"
    return content, None


def _tokens(value: str) -> list[str]:
    # Preserve API identifiers, split CamelCase/snake_case, and index CJK bigrams.
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", value).lower()
    tokens = re.findall(r"[a-z][a-z0-9_]{1,79}|[0-9]{1,10}", value)
    result = list(tokens)
    for token in tokens:
        result.extend(part for part in token.split("_") if len(part) > 1 and part != token)
    for phrase in re.findall(r"[\u3400-\u9fff]+", value):
        if len(phrase) == 1:
            result.append(phrase)
        else:
            result.extend(phrase[index:index + 2] for index in range(len(phrase) - 1))
    return result


def _chunks(content: str):
    lines = content.splitlines()
    start = 0
    while start < len(lines):
        end = start
        size = 0
        while end < len(lines) and end - start < 60:
            if end > start and size + len(lines[end]) > 6000:
                break
            size += len(lines[end]) + 1
            end += 1
        body = "\n".join(lines[start:end])
        # A compact/minified JSON line still gets bounded retrieval passages.
        for offset in range(0, max(len(body), 1), 6000):
            yield start + 1, end, body[offset:offset + 6000]
        start = max(start + 1, end - 8) if end < len(lines) and end - start > 8 else end


class KnowledgeStore:
    """Thread-safe SQLite index plus sanitized snapshots of explicitly chosen code."""

    def __init__(self, directory: Path):
        self.root = Path(directory).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.snapshots = self.root / "snapshots"
        self.snapshots.mkdir(exist_ok=True)
        self._lock = RLock()
        self.connection = sqlite3.connect(self.root / "knowledge.sqlite3", check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA foreign_keys=ON")
        self.connection.execute("PRAGMA busy_timeout=5000")
        self.connection.executescript("""
            CREATE TABLE IF NOT EXISTS repositories (
                id TEXT PRIMARY KEY, source_path TEXT UNIQUE, payload TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS files (
                repository_id TEXT NOT NULL REFERENCES repositories(id),
                path TEXT NOT NULL, digest TEXT NOT NULL,
                PRIMARY KEY(repository_id,path)
            );
            CREATE TABLE IF NOT EXISTS chunks (
                id INTEGER PRIMARY KEY, repository_id TEXT NOT NULL REFERENCES repositories(id),
                path TEXT NOT NULL, start_line INTEGER NOT NULL, end_line INTEGER NOT NULL,
                content TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS chunks_repository ON chunks(repository_id,path);
            CREATE TABLE IF NOT EXISTS feedback (
                id TEXT PRIMARY KEY, repository_id TEXT NOT NULL REFERENCES repositories(id),
                payload TEXT NOT NULL
            );
        """)
        try:
            self.connection.execute("CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(tokens)")
            self._fts = True
        except sqlite3.OperationalError:
            self._fts = False
        self.connection.commit()

    def close(self):
        with self._lock:
            self.connection.close()

    def list(self) -> list[dict]:
        with self._lock:
            rows = self.connection.execute("SELECT payload FROM repositories").fetchall()
            return sorted((json.loads(row[0]) for row in rows), key=lambda item: item["updated_at"], reverse=True)

    def get(self, repository_id: str) -> dict | None:
        with self._lock:
            row = self.connection.execute("SELECT payload FROM repositories WHERE id=?", (repository_id,)).fetchone()
            return json.loads(row[0]) if row else None

    def _require(self, repository_id: str) -> dict:
        item = self.get(repository_id)
        if item is None:
            raise KeyError("代码库不存在。")
        return item

    def project_root(self, repository_id: str) -> Path:
        item = self._require(repository_id)
        return self.snapshots / item["id"] / str(item["revision"])

    def _validate_source(self, source: str | Path) -> Path:
        path = Path(source).expanduser()
        if not path.is_absolute():
            raise ValueError("请选择代码库的绝对路径，不会隐式扫描当前目录。")
        if path.is_symlink():
            raise ValueError("不能导入符号链接目录。")
        path = path.resolve(strict=True)
        if not path.is_dir():
            raise ValueError("请选择现有代码库目录。")
        if path in {Path("/"), Path.home(), Path("/home"), Path("/Users"), Path("/mnt"), Path("/media"), Path("/tmp")}:
            raise ValueError("请选择具体的代码库子目录，不能导入整个主目录或磁盘。")
        for blocked in (Path("/etc"), Path("/proc"), Path("/sys"), Path("/dev"), Path("/var"), Path("/usr"), Path("/root")):
            if path == blocked or path.is_relative_to(blocked):
                raise ValueError("不能导入系统目录。")
        if any(part.lower() in IGNORED_DIRS or part.startswith(".") for part in path.parts[1:]):
            raise ValueError("不能导入隐藏、凭据或构建目录。")
        if path == self.root or path.is_relative_to(self.root):
            raise ValueError("不能导入知识库自身。")
        return path

    def _read_local(self, root: Path) -> tuple[dict[str, bytes], Counter]:
        result: dict[str, bytes] = {}
        skipped: Counter = Counter()
        total = entries = 0
        # fwalk + relative no-follow opens avoid following symlinks even if the
        # directory is being edited while we take the snapshot (POSIX host).
        root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            for current, dirs, files, directory_fd in os.fwalk(".", dir_fd=root_fd, follow_symlinks=False):
                entries += len(dirs) + len(files)
                if entries > MAX_ENTRIES:
                    raise ValueError(f"目录超过 {MAX_ENTRIES} 个条目，请选择更小的代码库。")
                relative_dir = Path(current)
                retained = []
                for name in sorted(dirs):
                    relative = relative_dir / name
                    full = root / relative
                    if name.lower() in IGNORED_DIRS or (name.startswith(".") and name != ".vscode") or full == self.root:
                        skipped["ignored_directory"] += 1
                        continue
                    try:
                        info = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
                        if not stat.S_ISDIR(info.st_mode):
                            skipped["symlink"] += 1
                            continue
                    except FileNotFoundError:
                        continue
                    retained.append(name)
                dirs[:] = retained
                for name in sorted(files):
                    relative = PurePosixPath((relative_dir / name).as_posix())
                    if not _allowed_file(relative):
                        skipped["excluded_path"] += 1
                        continue
                    try:
                        descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory_fd)
                    except OSError:
                        skipped["unreadable_or_link"] += 1
                        continue
                    with os.fdopen(descriptor, "rb") as handle:
                        info = os.fstat(handle.fileno())
                        if not stat.S_ISREG(info.st_mode) or info.st_nlink > 1:
                            skipped["special_or_link"] += 1
                            continue
                        if info.st_size > MAX_FILE_BYTES:
                            skipped["oversized_file"] += 1
                            continue
                        data = handle.read(MAX_FILE_BYTES + 1)
                    if len(data) > MAX_FILE_BYTES:
                        raise ValueError("文件在读取过程中超过大小限制。")
                    content, reason = _decode(data)
                    if content is None:
                        skipped[reason] += 1
                        continue
                    total += len(data)
                    if len(result) >= MAX_FILES or total > MAX_TOTAL_BYTES:
                        raise ValueError(f"索引最多支持 {MAX_FILES} 个文本文件、50 MiB 总量。")
                    result[str(relative)] = data
        finally:
            os.close(root_fd)
        return result, skipped

    def import_path(self, path: str | Path, name: str | None = None) -> dict:
        with self._lock:
            source = self._validate_source(path)
            files, skipped = self._read_local(source)
            row = self.connection.execute("SELECT id FROM repositories WHERE source_path=?", (str(source),)).fetchone()
            previous = self.get(row[0]) if row else None
            return self._save(files, _safe_name(name, previous["name"] if previous else source.name), "local", str(source), skipped, previous)

    def import_zip(self, payload: bytes, name: str = "uploaded-repository") -> dict:
        if len(payload) > MAX_UPLOAD_BYTES:
            raise ValueError("ZIP 上传不得超过 20 MiB。")
        display_name = _safe_name(name, "uploaded-repository")
        files: dict[str, bytes] = {}
        skipped: Counter = Counter()
        declared_size = actual_size = 0
        with self._lock:
            try:
                archive = zipfile.ZipFile(io.BytesIO(payload))
            except zipfile.BadZipFile:
                raise ValueError("请上传有效的 ZIP 文件。") from None
            with archive:
                members = archive.infolist()
                if len(members) > MAX_ENTRIES:
                    raise ValueError("ZIP 条目数量超过限制。")
                seen: set[str] = set()
                for member in members:
                    raw = member.filename
                    path = PurePosixPath(raw)
                    if not raw or "\x00" in raw or "\\" in raw or path.is_absolute() or ".." in path.parts or ":" in raw or len(raw) > 1024:
                        raise ValueError("ZIP 中包含不安全的路径。")
                    normalized = str(path)
                    if normalized in seen:
                        raise ValueError("ZIP 中包含重复路径。")
                    seen.add(normalized)
                    mode = member.external_attr >> 16
                    if stat.S_ISLNK(mode) or (stat.S_IFMT(mode) and not stat.S_ISREG(mode) and not stat.S_ISDIR(mode)):
                        raise ValueError("ZIP 中不能包含符号链接或特殊文件。")
                    if member.flag_bits & 1:
                        raise ValueError("不支持加密 ZIP。")
                    declared_size += member.file_size
                    if declared_size > MAX_TOTAL_BYTES:
                        raise ValueError("ZIP 解压总大小不得超过 50 MiB。")
                    if member.is_dir():
                        continue
                    if not _allowed_file(path):
                        skipped["excluded_path"] += 1
                        continue
                    if member.file_size > MAX_FILE_BYTES:
                        skipped["oversized_file"] += 1
                        continue
                    try:
                        with archive.open(member) as handle:
                            data = handle.read(MAX_FILE_BYTES + 1)
                    except (zipfile.BadZipFile, NotImplementedError, RuntimeError, EOFError):
                        raise ValueError("ZIP 损坏或压缩格式不受支持。") from None
                    if len(data) > MAX_FILE_BYTES:
                        raise ValueError("ZIP 文件解压大小超过限制。")
                    actual_size += len(data)
                    if actual_size > MAX_TOTAL_BYTES:
                        raise ValueError("ZIP 解压总大小不得超过 50 MiB。")
                    content, reason = _decode(data)
                    if content is None:
                        skipped[reason] += 1
                        continue
                    if len(files) >= MAX_FILES:
                        raise ValueError(f"索引最多支持 {MAX_FILES} 个文本文件。")
                    files[normalized] = data
            # GitHub/downloaded repository ZIPs commonly have one wrapper folder.
            parts = [PurePosixPath(path).parts for path in files]
            if parts and all(len(path) > 1 and path[0] == parts[0][0] for path in parts):
                files = {str(PurePosixPath(*PurePosixPath(path).parts[1:])): data for path, data in files.items()}
            return self._save(files, display_name, "zip", None, skipped)

    def _save(self, files: dict[str, bytes], name: str, source_type: str,
              source_path: str | None, skipped: Counter, previous: dict | None = None) -> dict:
        if not files and previous is None:
            raise ValueError("没有可索引的 UTF-8 代码或文档；凭据、二进制、隐藏和构建文件会被排除。")
        repository_id = previous["id"] if previous else uuid.uuid4().hex
        old_files = dict(self.connection.execute("SELECT path,digest FROM files WHERE repository_id=?", (repository_id,)).fetchall())
        digests = {path: hashlib.sha256(data).hexdigest() for path, data in files.items()}
        added = set(digests) - set(old_files)
        deleted = set(old_files) - set(digests)
        changed = {path for path in set(digests) & set(old_files) if digests[path] != old_files[path]}
        revision = previous["revision"] if previous else 0
        has_changes = bool(added or deleted or changed)
        if has_changes:
            revision += 1
        now = _now()
        item = {
            "id": repository_id, "name": name, "source_type": source_type, "source_path": source_path,
            "revision": revision, "file_count": len(files), "chunk_count": 0,
            "total_bytes": sum(len(data) for data in files.values()),
            "created_at": previous["created_at"] if previous else now, "updated_at": now,
            "stats": {"added": len(added), "changed": len(changed), "deleted": len(deleted),
                      "unchanged": len(files) - len(added) - len(changed), "skipped": dict(skipped)},
            "learning_mode": "retrieval_and_reviewed_experience",
        }
        destination = self.snapshots / repository_id / str(revision)
        if has_changes:
            destination.parent.mkdir(parents=True, exist_ok=True)
            temporary = Path(tempfile.mkdtemp(prefix=".import-", dir=destination.parent))
            try:
                for relative, data in files.items():
                    target = temporary / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(data)
                os.replace(temporary, destination)
            except BaseException:
                shutil.rmtree(temporary, ignore_errors=True)
                raise
        try:
            with self.connection:
                self.connection.execute(
                    "INSERT INTO repositories(id,source_path,payload) VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload",
                    (repository_id, source_path, json.dumps(item, ensure_ascii=False)),
                )
                for path in deleted | changed:
                    ids = self.connection.execute("SELECT id FROM chunks WHERE repository_id=? AND path=?", (repository_id, path)).fetchall()
                    if self._fts:
                        self.connection.executemany("DELETE FROM chunks_fts WHERE rowid=?", [(row[0],) for row in ids])
                    self.connection.execute("DELETE FROM chunks WHERE repository_id=? AND path=?", (repository_id, path))
                    self.connection.execute("DELETE FROM files WHERE repository_id=? AND path=?", (repository_id, path))
                for path in sorted(added | changed):
                    self.connection.execute("INSERT INTO files(repository_id,path,digest) VALUES(?,?,?)", (repository_id, path, digests[path]))
                    content = files[path].decode("utf-8-sig")
                    for start, end, body in _chunks(content):
                        cursor = self.connection.execute(
                            "INSERT INTO chunks(repository_id,path,start_line,end_line,content) VALUES(?,?,?,?,?)",
                            (repository_id, path, start, end, body),
                        )
                        if self._fts:
                            self.connection.execute("INSERT INTO chunks_fts(rowid,tokens) VALUES(?,?)",
                                                    (cursor.lastrowid, " ".join(_tokens(path + "\n" + body))))
                item["chunk_count"] = self.connection.execute("SELECT count(*) FROM chunks WHERE repository_id=?", (repository_id,)).fetchone()[0]
                self.connection.execute("UPDATE repositories SET payload=? WHERE id=?", (json.dumps(item, ensure_ascii=False), repository_id))
        except BaseException:
            if has_changes:
                shutil.rmtree(destination, ignore_errors=True)
            raise
        return item

    def reindex(self, repository_id: str) -> dict:
        with self._lock:
            item = self._require(repository_id)
            if item["source_type"] == "local":
                return self.import_path(item["source_path"], item["name"])
            # ZIP has no live external source: reindex its sanitized snapshot.
            files, skipped = self._read_local(self.project_root(repository_id))
            return self._save(files, item["name"], "zip", None, skipped, item)

    def add_feedback(self, repository_id: str, title: str, content: str, accepted: bool = False,
                     evidence: str | dict | None = None, revision: int | None = None) -> dict:
        with self._lock:
            repository = self._require(repository_id)
            revision = repository["revision"] if revision is None else revision
            if type(revision) is not int or revision < 1 or revision > repository["revision"] or not (self.snapshots / repository_id / str(revision)).is_dir():
                raise ValueError("经验关联的代码库版本不存在。")
            title = title.strip()
            content = content.strip()
            if not title or len(title) > 200 or not content or len(content) > 20000:
                raise ValueError("经验标题限 1–200 字，正文限 1–20000 字。")
            if type(accepted) is not bool:
                raise ValueError("accepted 必须为布尔值。")
            if evidence is not None and not isinstance(evidence, (str, dict)):
                raise ValueError("evidence 必须为字符串或对象。")
            if len(json.dumps(evidence, ensure_ascii=False)) > 8000:
                raise ValueError("证据内容过长。")
            if accepted and (evidence is None or not evidence or (isinstance(evidence, str) and not evidence.strip())):
                raise ValueError("接纳经验前必须填写验证证据或代码引用。")
            text, reason = _decode((title + "\n" + content + "\n" + json.dumps(evidence, ensure_ascii=False)).encode("utf-8"))
            if text is None:
                raise ValueError("经验内容疑似包含密钥或凭据，请移除后再保存。")
            item = {"id": uuid.uuid4().hex, "repository_id": repository_id, "title": title,
                    "content": content, "accepted": accepted, "evidence": evidence,
                    "revision": revision, "created_at": _now()}
            with self.connection:
                self.connection.execute("INSERT INTO feedback(id,repository_id,payload) VALUES(?,?,?)",
                                        (item["id"], repository_id, json.dumps(item, ensure_ascii=False)))
            return item

    def review_feedback(self, repository_id: str, feedback_id: str, accepted: bool,
                        evidence: str | dict | None = None) -> dict:
        with self._lock:
            self._require(repository_id)
            row = self.connection.execute("SELECT payload FROM feedback WHERE repository_id=? AND id=?",
                                          (repository_id, feedback_id)).fetchone()
            if not row:
                raise KeyError("经验不存在。")
            item = json.loads(row[0])
            if type(accepted) is not bool:
                raise ValueError("accepted 必须为布尔值。")
            evidence = item["evidence"] if evidence is None else evidence
            if evidence is not None and not isinstance(evidence, (str, dict)):
                raise ValueError("evidence 必须为字符串或对象。")
            if len(json.dumps(evidence, ensure_ascii=False)) > 8000:
                raise ValueError("证据内容过长。")
            if accepted and (not evidence or (isinstance(evidence, str) and not evidence.strip())):
                raise ValueError("接纳经验前必须填写验证证据或代码引用。")
            content, _ = _decode(json.dumps(evidence, ensure_ascii=False).encode("utf-8"))
            if content is None:
                raise ValueError("证据疑似包含密钥或凭据，请移除后再保存。")
            item.update(accepted=accepted, evidence=evidence, reviewed_at=_now())
            with self.connection:
                self.connection.execute("UPDATE feedback SET payload=? WHERE repository_id=? AND id=?",
                                        (json.dumps(item, ensure_ascii=False), repository_id, feedback_id))
            return item

    def search_all(self, query: str, limit: int = 6) -> list[dict]:
        """Read-only evidence across the library; never copy example projects into output."""
        hits = []
        for repo in self.list():
            for hit in self.search(repo['id'], query[:4000], limit=limit):
                hits.append({**hit, 'repository_id': repo['id'], 'repository_name': repo['name'],
                             'repository_revision': repo['revision'], 'content': hit['content'][:1600]})
        hits.sort(key=lambda hit: hit.get('score', 0), reverse=True)
        return hits[:limit]

    def context(self, repository_id: str, query: str, limit: int = 6) -> dict:
        """Return one coherent revision; immutable roots remain valid after reindex."""
        with self._lock:
            repository = self._require(repository_id)
            return {"repository": repository, "root": self.project_root(repository_id),
                    "hits": self.search(repository_id, query, limit)}

    def feedback(self, repository_id: str) -> list[dict]:
        with self._lock:
            self._require(repository_id)
            rows = self.connection.execute("SELECT payload FROM feedback WHERE repository_id=? ORDER BY rowid DESC", (repository_id,)).fetchall()
            return [json.loads(row[0]) for row in rows]

    def search(self, repository_id: str, query: str, limit: int = 6) -> list[dict]:
        with self._lock:
            repository = self._require(repository_id)
            if not isinstance(query, str) or len(query) > 4000:
                raise ValueError("检索问题不得超过 4000 字。")
            terms = set(_tokens(query))
            if not terms:
                return []
            terms = set(sorted(terms)[:64])
            limit = max(1, min(int(limit), 20))
            if self._fts:
                expression = " OR ".join('"' + token.replace('"', '""') + '"' for token in sorted(terms))
                rows = self.connection.execute(
                    "SELECT c.* FROM chunks_fts JOIN chunks c ON c.id=chunks_fts.rowid "
                    "WHERE chunks_fts MATCH ? AND c.repository_id=? ORDER BY bm25(chunks_fts) LIMIT 100",
                    (expression, repository_id),
                ).fetchall()
            else:
                rows = self.connection.execute("SELECT * FROM chunks WHERE repository_id=?", (repository_id,)).fetchall()
            results = []
            for row in rows:
                token_counts = Counter(_tokens(row["path"] + "\n" + row["content"]))
                matched = terms & token_counts.keys()
                if not matched:
                    continue
                score = sum(1 + math.log1p(token_counts[term]) for term in matched) / math.sqrt(max(len(token_counts), 1))
                score += 2 * len(matched) / len(terms)
                results.append({"path": row["path"], "start_line": row["start_line"], "end_line": row["end_line"],
                                "content": row["content"], "score": round(score, 6), "source": "repository",
                                "revision": repository["revision"]})
            for experience in self.feedback(repository_id):
                if not experience["accepted"]:
                    continue
                text = experience["title"] + "\n" + experience["content"]
                matched = terms & set(_tokens(text))
                if not matched:
                    continue
                results.append({"path": "experience:" + experience["id"], "start_line": 1,
                                "end_line": len(text.splitlines()), "content": text[:6000],
                                "score": round(3 * len(matched) / len(terms), 6), "source": "feedback",
                                "revision": experience["revision"], "evidence": experience["evidence"]})
            return sorted(results, key=lambda item: (-item["score"], item["path"], item["start_line"]))[:limit]
