#!/usr/bin/env python3
"""Read-only ModSDK artifact checks. Does not import or execute project code.

Python 2 checks are deliberately incomplete: host Python 3 is not its parser.
The public validate_project contract is consumed by the development pipeline.
"""
from __future__ import annotations

import argparse
import ast
import io
import json
import math
import os
import re
import tokenize
from pathlib import Path

EXCLUDED = {".git", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache", ".mypy_cache"}
MAX_FILES = 1000
MAX_FILE_BYTES = 1024 * 1024
MAX_TOTAL_BYTES = 20 * 1024 * 1024


def _pairs(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("重复 JSON 键: " + key)
        value[key] = item
    return value


def _constant(value):
    raise ValueError("JSON 不允许非有限数值: " + value)


def _float(value):
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("JSON 数值超出有限浮点数范围: " + value)
    return result


def _python_checks(source: str, filename: str, runtime: str) -> list[dict]:
    results = []

    def add(level, message, line=None):
        prefix = f"第 {line} 行：" if line else ""
        entry = {"path": filename, "level": level, "message": prefix + message}
        if entry not in results:
            results.append(entry)

    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(source).readline))
    except (tokenize.TokenError, IndentationError, SyntaxError) as exc:
        add("error", "无法完成词法分析: " + str(exc))
        return results

    tree = None
    try:
        tree = ast.parse(source, filename=filename)
    except (SyntaxError, ValueError, RecursionError) as exc:
        if runtime == "python3":
            add("error", "当前主机 Python 3 语法解析失败: " + str(exc), getattr(exc, "lineno", None))
        else:
            add("warning", "主机 Python 3 无法解析此脚本；可能是合法 Python 2 语法，须由目标 Python 2 解析器核验。")

    if runtime == "python2":
        for token in tokens:
            if token.type == tokenize.STRING and re.match(r"(?i)^[rubf]*f[rubf]*['\"]", token.string):
                add("error", "Python 2 不支持 f-string。", token.start[0])
            if tokenize.tok_name.get(token.type) == "FSTRING_START":
                add("error", "Python 2 不支持 f-string。", token.start[0])
            if token.type == tokenize.NUMBER and "_" in token.string:
                add("error", "Python 2 不支持数字字面量中的下划线。", token.start[0])
        if tree is not None:
            unsupported = (ast.AnnAssign, ast.AsyncFunctionDef, ast.AsyncFor, ast.AsyncWith,
                           ast.Await, ast.NamedExpr, ast.Nonlocal, ast.YieldFrom)
            for node in ast.walk(tree):
                if isinstance(node, unsupported):
                    add("error", "Python 2 不支持此语法: " + type(node).__name__, getattr(node, "lineno", None))
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                    args = node.args
                    parameters = args.posonlyargs + args.args + args.kwonlyargs
                    if args.vararg:
                        parameters.append(args.vararg)
                    if args.kwarg:
                        parameters.append(args.kwarg)
                    if any(arg.annotation is not None for arg in parameters) or getattr(node, "returns", None) is not None:
                        add("error", "Python 2 不支持函数类型注解。", node.lineno)
                    if args.kwonlyargs or args.posonlyargs:
                        add("error", "Python 2 不支持此 keyword-only / positional-only 参数语法。", node.lineno)
                if isinstance(node, ast.Raise) and node.cause is not None:
                    add("error", "Python 2 不支持 raise ... from ...。", node.lineno)
                if isinstance(node, ast.Dict) and any(key is None for key in node.keys):
                    add("error", "Python 2 不支持字典字面量解包。", node.lineno)
                if isinstance(node, ast.BinOp) and isinstance(node.op, ast.MatMult):
                    add("error", "Python 2 不支持矩阵乘法运算符。", node.lineno)
                if isinstance(node, ast.ClassDef) and node.keywords:
                    add("error", "Python 2 不支持类定义关键字参数。", node.lineno)
        if any(ord(char) > 127 for char in source):
            header = "\n".join(source.splitlines()[:2])
            if not re.search(r"^[ \t\f]*#.*?coding[:=]\s*[-\w.]+", header, re.M):
                add("error", "Python 2 源码包含非 ASCII 字符但前两行没有编码声明。")

    if tree is not None:
        # Only clearly named side modules are classified; modMain can initialize both sides.
        path = Path(filename)
        parts = {part.lower() for part in path.parts[:-1]}
        stem = path.stem.lower()
        side = "server" if "server" in parts or stem in {"server", "serversystem"} or stem.endswith("serversystem") else None
        if "client" in parts or stem in {"client", "clientsystem"} or stem.endswith("clientsystem"):
            side = "client" if side is None else None
        if stem == "modmain":
            side = None
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""] + [(node.module + "." if node.module else "") + alias.name for alias in node.names]
            wrong = "mod.client" if side == "server" else "mod.server" if side == "client" else None
            if wrong and any(name == wrong or name.startswith(wrong + ".") for name in names):
                add("error", f"文件名/目录标示为 {side}，却导入 {wrong}；请核对端别。", node.lineno)
    return results


def validate_project(root: Path, runtime: str) -> list[dict]:
    """Return [{path, level: error|warning|info, message}]; never run source code.

    runtime is python2 or python3. Errors mean known static defects or incomplete
    scanning due to hard limits. Warnings retain unverified runtime/API boundaries.
    """
    results = []

    def add(path, level, message):
        results.append({"path": path, "level": level, "message": message})

    if runtime not in {"python2", "python3"}:
        add(".", "error", "runtime 必须为 python2 或 python3。")
        return results
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        add(".", "error", "校验根目录必须是实际目录，不能是符号链接。")
        return results
    root = root.resolve()
    count = 0
    total = 0
    found_python = False

    def walk_error(exc):
        add(".", "error", "无法枚举部分目录: " + str(exc))

    for folder, dirs, files in os.walk(root, followlinks=False, onerror=walk_error):
        for name in sorted(dirs):
            path = Path(folder) / name
            if path.is_symlink():
                add(path.relative_to(root).as_posix(), "error", "不读取符号链接目录。")
        dirs[:] = sorted(name for name in dirs if name not in EXCLUDED and not (Path(folder) / name).is_symlink())
        for name in sorted(files):
            path = Path(folder) / name
            relative = path.relative_to(root).as_posix()
            if path.is_symlink():
                add(relative, "error", "不读取符号链接文件。")
                continue
            if not path.is_file():
                add(relative, "error", "不读取特殊文件。")
                continue
            if path.suffix.lower() not in {".py", ".json"}:
                continue
            count += 1
            if count > MAX_FILES:
                add(".", "error", f"超过 {MAX_FILES} 个代码/JSON 文件，校验未完成。")
                return results
            try:
                size = path.stat().st_size
                total += size
                if size > MAX_FILE_BYTES or total > MAX_TOTAL_BYTES:
                    add(relative, "error", "超过单文件 1 MiB 或合计 20 MiB 的校验上限，校验未完成。")
                    continue
                # Bound the actual read too in case files change between stat and read.
                with path.open("rb") as stream:
                    payload = stream.read(MAX_FILE_BYTES + 1)
                if len(payload) > MAX_FILE_BYTES:
                    add(relative, "error", "读取时超过单文件校验上限。")
                    continue
                if path.suffix.lower() == ".json":
                    value = json.loads(payload.decode("utf-8-sig"), object_pairs_hook=_pairs, parse_constant=_constant, parse_float=_float)
                    if path.name == "manifest.json" and not isinstance(value, dict):
                        add(relative, "error", "manifest.json 顶层必须是对象；未核验目标版本完整 schema。")
                else:
                    found_python = True
                    encoding, _ = tokenize.detect_encoding(io.BytesIO(payload).readline)
                    results.extend(_python_checks(payload.decode(encoding), relative, runtime))
            except (OSError, UnicodeError, LookupError, SyntaxError, ValueError, RecursionError) as exc:
                add(relative, "error", "文件读取/解析失败: " + str(exc))
    if not count:
        add(".", "warning", "没有找到 Python/JSON 产物。")
    if found_python and runtime == "python2":
        add(".", "warning", "Python 2 仅完成有限静态检查；未运行 Python 2 解析器或网易游戏运行时，不能据此宣称兼容。")
    add(".", "info", f"已检查 {count} 个 Python/JSON 文件；未执行项目代码，未验证 SDK API 存在性、游戏效果或完整资源 schema。")
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--runtime", required=True, choices=["python2", "python3"])
    args = parser.parse_args()
    results = validate_project(args.root, args.runtime)
    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 1 if any(row["level"] == "error" for row in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
