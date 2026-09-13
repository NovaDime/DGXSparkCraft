"""Windows local service lifecycle. No extra dependencies beyond the application."""
from __future__ import annotations

import argparse
import asyncio
from collections import Counter, deque
from contextlib import contextmanager
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.request
import uuid
import webbrowser

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
DEFAULT_RUNTIME = ROOT / "artifacts/runtime"
STATE_NAME = "service.json"


def stamp():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None


def write_json(path, value):
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)


@contextmanager
def manager_lock(runtime):
    import msvcrt
    runtime.mkdir(parents=True, exist_ok=True)
    with (runtime / "manager.lock").open("a+b") as stream:
        if stream.seek(0, 2) == 0:
            stream.write(b"0")
            stream.flush()
        stream.seek(0)
        try:
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            raise RuntimeError("另一个启动或关闭操作正在进行，请稍后重试。") from None
        try:
            yield
        finally:
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)


class ProcessHandle:
    """Use one Windows handle for identity checks and termination (PID reuse safe)."""
    def __init__(self, pid, terminate=False):
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        self.kernel.OpenProcess.restype = wintypes.HANDLE
        self.kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        self.kernel.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
        self.kernel.GetProcessTimes.restype = wintypes.BOOL
        self.kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        self.kernel.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
        self.kernel.TerminateProcess.restype = wintypes.BOOL
        self.kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        self.handle = self.kernel.OpenProcess(0x1000 | 0x100000 | (1 if terminate else 0), False, pid)
        if not self.handle:
            error = ctypes.get_last_error()
            if error in (87, 1168):
                raise ProcessLookupError(pid)
            raise OSError(error, "无法查询服务进程；不会结束身份未确认的进程。")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.kernel.CloseHandle(self.handle)

    def identity(self):
        created, ended, kernel, user = (wintypes.FILETIME() for _ in range(4))
        if not self.kernel.GetProcessTimes(self.handle, ctypes.byref(created), ctypes.byref(ended),
                                           ctypes.byref(kernel), ctypes.byref(user)):
            raise OSError("无法验证服务进程创建时间。")
        return str((created.dwHighDateTime << 32) | created.dwLowDateTime)

    def alive(self):
        return self.kernel.WaitForSingleObject(self.handle, 0) == 258

    def terminate(self):
        if not self.kernel.TerminateProcess(self.handle, 1):
            raise OSError("结束进程失败，请查看进程权限。")
        if self.kernel.WaitForSingleObject(self.handle, 5000) != 0:
            raise RuntimeError("进程仍未退出，请查看状态后处理。")


def process_matches(state):
    if not state or state.get("project_root") != str(ROOT) or not state.get("pid"):
        return False
    try:
        with ProcessHandle(state["pid"]) as process:
            return process.alive() and process.identity() == state.get("process_created")
    except ProcessLookupError:
        return False


def request_json(port, path):
    # Loopback requests must not inherit corporate or user HTTP proxies.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(f"http://127.0.0.1:{port}{path}", timeout=1) as response:
            return json.load(response)
    except (OSError, ValueError):
        return None


def health(port):
    value = request_json(port, "/api/health")
    return value if isinstance(value, dict) and value.get("ok") is True and value.get("provider_mode") in {"simulation", "openclaw"} else None


def port_available(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        try:
            listener.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def owned_path(state, key):
    path = Path(state[key]).resolve()
    if not path.is_relative_to(ROOT / "artifacts"):
        raise RuntimeError("运行日志路径不在本项目 artifacts 目录内。")
    return path


def update_state(runtime, instance, **changes):
    state = read_json(runtime / STATE_NAME)
    if state and state.get("instance") == instance:
        state.update(changes)
        write_json(runtime / STATE_NAME, state)


async def run_server(runtime, instance):
    state = read_json(runtime / STATE_NAME)
    if not state or state.get("instance") != instance:
        raise RuntimeError("启动记录已改变，本次启动取消。")
    with ProcessHandle(os.getpid()) as process:
        update_state(runtime, instance, pid=os.getpid(), process_created=process.identity())
    import uvicorn
    from roundtable.app import create_app
    from roundtable.config import Settings
    config = Settings.from_env()
    update_state(runtime, instance, data_dir=str(config.data_dir), provider_mode=config.provider_mode)
    server = uvicorn.Server(uvicorn.Config(create_app(config), host="127.0.0.1", port=state["port"],
                            workers=1, log_level="info", timeout_graceful_shutdown=5))

    async def watch_stop():
        announced = False
        while True:
            command = read_json(runtime / "stop.json")
            if command and command.get("instance") == instance:
                update_state(runtime, instance, phase="stopping")
                server.should_exit = True
                return
            if server.started and not announced:
                update_state(runtime, instance, phase="running", ready_at=stamp())
                announced = True
            await asyncio.sleep(.25)

    watcher = asyncio.create_task(watch_stop())
    try:
        await server.serve()
        update_state(runtime, instance, phase="stopped" if server.started else "failed", stopped_at=stamp())
    finally:
        watcher.cancel()
        await asyncio.gather(watcher, return_exceptions=True)


def stop_owned(runtime, state, timeout):
    if not process_matches(state):
        print("服务进程已退出，没有需要结束的受管进程。")
        return
    write_json(runtime / "stop.json", {"instance": state["instance"], "requested_at": stamp()})
    print(f"正在关闭本项目服务（PID {state['pid']}），等待保存会议…", flush=True)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not process_matches(state):
            finish_launcher(runtime, state)
            print("服务已正常退出，会议记录与日志已保留。")
            return
        time.sleep(.2)
    try:
        with ProcessHandle(state["pid"], terminate=True) as process:
            if process.identity() != state["process_created"]:
                raise RuntimeError("PID 已被其他进程使用，已拒绝结束该进程。")
            if process.alive():
                process.terminate()
    except ProcessLookupError:
        pass
    update_state(runtime, state["instance"], phase="forced_stop", stopped_at=stamp())
    finish_launcher(runtime, state)
    print("关闭等待超时，已结束本项目服务。已落盘记录保留；未完成会议将在下次启动时标记中断。")


def finish_launcher(runtime, state):
    # Windows venv python.exe may be a redirector waiting for the real Python child.
    launcher = read_json(runtime / "launcher.json")
    if not launcher or launcher.get("instance") != state["instance"] or launcher["pid"] == state["pid"]:
        return
    if not process_matches(launcher):
        return
    with ProcessHandle(launcher["pid"], terminate=True) as process:
        if process.identity() != launcher["process_created"]:
            return
        if process.kernel.WaitForSingleObject(process.handle, 1000) == 258:
            process.terminate()


def start(args):
    from roundtable.config import Settings
    # Validate config and dependencies before creating a background process.
    import fastapi, uvicorn, httpx, pydantic  # noqa: F401
    Settings.from_env()
    runtime = args.runtime_dir
    with manager_lock(runtime):
        previous = read_json(runtime / STATE_NAME)
        if process_matches(previous):
            if previous["port"] != args.port:
                raise RuntimeError(f"本项目已在端口 {previous['port']} 运行；换端口前请先关闭。")
            if not health(previous["port"]):
                raise RuntimeError("受管进程存在但服务无响应，请查看日志或先关闭再启动。")
            print(f"服务已经运行：{previous['url']}（PID {previous['pid']}），没有重复启动。")
            if not args.no_browser:
                webbrowser.open(previous["url"])
            return
        if not port_available(args.port):
            raise RuntimeError(f"端口 {args.port} 已被占用。可能是之前手动启动的服务；请在原终端关闭，或使用 --port 指定其他端口。不会结束未知进程。")
        instance = uuid.uuid4().hex
        logs = ROOT / "artifacts/logs"
        logs.mkdir(parents=True, exist_ok=True)
        name = datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + instance[:8]
        state = {"project_root": str(ROOT), "instance": instance, "pid": None,
                 "process_created": None, "phase": "starting", "started_at": stamp(),
                 "port": args.port, "url": f"http://127.0.0.1:{args.port}", "python": sys.executable,
                 "stdout_log": str(logs / f"{name}.stdout.log"), "stderr_log": str(logs / f"{name}.stderr.log")}
        write_json(runtime / STATE_NAME, state)
        environment = {**os.environ, "PYTHONUNBUFFERED": "1", "PYTHONUTF8": "1"}
        with Path(state["stdout_log"]).open("wb") as output, Path(state["stderr_log"]).open("wb") as errors:
            process = subprocess.Popen([sys.executable, "-u", str(Path(__file__).resolve()), "run",
                        "--runtime-dir", str(runtime), "--instance", instance], cwd=ROOT, env=environment,
                        stdin=subprocess.DEVNULL, stdout=output, stderr=errors, close_fds=True,
                        creationflags=subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP)
        with ProcessHandle(process.pid) as handle:
            write_json(runtime / "launcher.json", {"project_root": str(ROOT), "instance": instance,
                       "pid": process.pid, "process_created": handle.identity()})
        print("正在启动本地圆桌…", flush=True)
        deadline = time.monotonic() + args.wait
        while time.monotonic() < deadline:
            current = read_json(runtime / STATE_NAME)
            if process.poll() is not None:
                raise RuntimeError(f"启动失败，请查看：{state['stderr_log']}")
            if current.get("phase") == "running" and health(args.port):
                print(f"启动成功：{state['url']}\nPID：{current['pid']}\n运行模式：{current['provider_mode']}\n日志：{logs}")
                if not args.no_browser:
                    webbrowser.open(state["url"])
                return
            time.sleep(.25)
        stop_owned(runtime, read_json(runtime / STATE_NAME), 5)
        raise RuntimeError(f"等待服务就绪超时，已清理本次启动。请查看：{state['stderr_log']}")


def stop(args):
    with manager_lock(args.runtime_dir):
        state = read_json(args.runtime_dir / STATE_NAME)
        if not state:
            print("没有本脚本管理的服务记录。若曾手动运行 python -m roundtable，请在原终端按 Ctrl+C。")
            return
        stop_owned(args.runtime_dir, state, args.timeout)
        if not port_available(state["port"]):
            print(f"提示：端口 {state['port']} 仍被占用，可能属于其他服务；未结束该进程。")


def snapshot(runtime):
    state = read_json(runtime / STATE_NAME)
    if not state:
        return {"managed": False, "running": False, "message": "未找到受管服务记录，请先运行启动脚本。"}
    alive = process_matches(state)
    result = {"managed": True, "running": alive, "phase": state.get("phase"),
              "pid": state["pid"], "url": state["url"], "started_at": state["started_at"],
              "python": state["python"], "data_dir": state.get("data_dir"),
              "stdout_log": str(owned_path(state, "stdout_log")), "stderr_log": str(owned_path(state, "stderr_log")),
              "health": health(state["port"]) if alive else None}
    meetings = request_json(state["port"], "/api/meetings") if result["health"] else None
    if isinstance(meetings, list):
        result["meetings"] = dict(Counter(item["status"] for item in meetings))
        result["active_meetings"] = [{key: item[key] for key in ("id", "status", "current_round", "max_rounds")}
                                     for item in meetings if item["status"] in {"running", "queued"}]
    return result


def show_snapshot(value):
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] AI 圆桌 · 日志与状态")
    if not value["managed"]:
        print(value["message"])
        return
    print(f"进程：{'运行中' if value['running'] else '已关闭'} | PID：{value['pid']} | 阶段：{value['phase']}")
    print(f"地址：{value['url']}\n启动时间（UTC）：{value['started_at']}\nPython：{value['python']}\n数据目录：{value['data_dir']}")
    report = value["health"]
    print(f"健康检查：{'正常' if report else '未连接'} | 模式：{report.get('provider_mode') if report else '—'}")
    if "meetings" in value:
        print("会议状态：" + (json.dumps(value["meetings"], ensure_ascii=False) or "{}"))
        for meeting in value["active_meetings"]:
            print(f"  {meeting['id'][:8]} · {meeting['status']} · 第 {meeting['current_round']}/{meeting['max_rounds']} 轮")
    print(f"标准输出：{value['stdout_log']}\n服务日志：{value['stderr_log']}")


def status(args):
    value = snapshot(args.runtime_dir)
    if args.json:
        print(json.dumps(value, ensure_ascii=False, indent=2))
        return
    show_snapshot(value)
    positions = {}

    def logs(current):
        for key in ("stdout_log", "stderr_log"):
            if key not in current:
                continue
            path = Path(current[key])
            if not path.exists():
                continue
            with path.open("r", encoding="utf-8", errors="replace") as stream:
                if str(path) not in positions:
                    lines = list(deque(stream, maxlen=args.lines))
                else:
                    stream.seek(positions[str(path)])
                    lines = stream.readlines()
                positions[str(path)] = stream.tell()
            if lines:
                print(f"\n--- {path.name} ---")
                print("".join(lines).rstrip())

    logs(value)
    if not args.follow:
        return
    print("\n每 2 秒检查状态与新日志。按 Ctrl+C 退出查看，不会关闭圆桌服务。", flush=True)
    previous = value
    while True:
        time.sleep(2)
        value = snapshot(args.runtime_dir)
        if value != previous:
            show_snapshot(value)
            previous = value
        logs(value)
        sys.stdout.flush()


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Windows 本地圆桌：启动、关闭、查看日志与状态")
    commands = parser.add_subparsers(dest="action", required=True)
    for action in ("start", "stop", "status", "run"):
        command = commands.add_parser(action)
        command.add_argument("--runtime-dir", type=Path, default=DEFAULT_RUNTIME)
        if action == "start":
            command.add_argument("--port", type=int, default=8765)
            command.add_argument("--no-browser", action="store_true")
            command.add_argument("--wait", type=float, default=20)
        elif action == "stop":
            command.add_argument("--timeout", type=float, default=15)
        elif action == "status":
            command.add_argument("--follow", action="store_true")
            command.add_argument("--json", action="store_true")
            command.add_argument("--lines", type=int, default=30)
        else:
            command.add_argument("--instance", required=True)
    args = parser.parse_args()
    if os.name != "nt":
        parser.error("这套管理脚本用于 Windows；Linux 使用 python -m roundtable 并由系统服务管理。")
    if args.action == "start" and (not 1 <= args.port <= 65535 or not 1 <= args.wait <= 120):
        parser.error("端口范围 1 至 65535，启动等待范围 1 至 120 秒。")
    if args.action == "stop" and not 0 <= args.timeout <= 120:
        parser.error("关闭等待范围 0 至 120 秒。")
    if args.action == "status" and not 0 <= args.lines <= 1000:
        parser.error("日志行数范围 0 至 1000。")
    args.runtime_dir = args.runtime_dir.resolve()
    try:
        if args.action == "run":
            try:
                asyncio.run(run_server(args.runtime_dir, args.instance))
            except BaseException:
                update_state(args.runtime_dir, args.instance, phase="failed", stopped_at=stamp())
                raise
        else:
            {"start": start, "stop": stop, "status": status}[args.action](args)
    except KeyboardInterrupt:
        print("\n已退出查看或操作。服务是否运行请通过 status 查询。")
    except (OSError, ValueError, RuntimeError, ImportError) as exc:
        print(f"操作失败：{exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
