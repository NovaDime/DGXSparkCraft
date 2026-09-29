"""Linux project-scoped start/stop/monitor; starts matching model dependencies; never stops vLLM or foreign gateways."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import socket
import sys
import time
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parent.parent
RUN = ROOT / "data" / "runtime"
PYTHON = ROOT / ".venv" / "bin" / "python"
SCRIPT = Path(__file__).resolve()

def processes():
    found = {"studio": [], "gateway": [], "launcher": [], "monitor": [], "startup": []}
    for folder in Path('/proc').iterdir():
        if not folder.name.isdigit() or int(folder.name) == os.getpid(): continue
        try:
            if (folder/'cwd').resolve() != ROOT: continue
            args = (folder/'cmdline').read_bytes().split(b'\0')
            words = [a.decode(errors='replace') for a in args if a]
            if not words: continue
            if any(a in ('scripts/run_studio.py', str(ROOT/'scripts/run_studio.py')) for a in words): kind='studio'
            elif any(a in ('scripts/setup_local_openclaw.py', str(ROOT/'scripts/setup_local_openclaw.py')) for a in words) and '--start' in words: kind='launcher'
            elif any(a == str(SCRIPT) for a in words) and 'watch' in words: kind='monitor'
            elif str(SCRIPT) in words and '--background-worker' in words: kind='startup'
            elif str(ROOT/'scripts/deploy_spark.py') in words: kind='startup'
            elif 'openclaw-gateway' in words[0]:
                env=(folder/'environ').read_bytes().split(b'\0')
                expected=b'OPENCLAW_CONFIG_PATH='+str(ROOT/'data/openclaw/openclaw.json').encode()
                if expected not in env: continue
                kind='gateway'
            else: continue
            found[kind].append(int(folder.name))
        except (OSError, ValueError): continue
    return found

def health():
    try:
        with urlopen('http://127.0.0.1:8765/api/health',timeout=3) as response:
            return bool(json.load(response).get('ok'))
    except Exception: return False

def existing_studio_root():
    """Identify the actual listener, not any similarly named process on this host."""
    inodes = set()
    for table in ('/proc/net/tcp', '/proc/net/tcp6'):
        try:
            for line in Path(table).read_text().splitlines()[1:]:
                fields = line.split()
                if fields[3] == '0A' and int(fields[1].split(':')[1], 16) == 8765:
                    inodes.add(fields[9])
        except OSError:
            continue
    if not inodes:
        return None
    for process in Path('/proc').iterdir():
        if not process.name.isdigit():
            continue
        try:
            if process.stat().st_uid != os.getuid():
                continue
            sockets = {os.readlink(fd) for fd in (process/'fd').iterdir()}
            if not any('socket:[' + inode + ']' in sockets for inode in inodes):
                continue
            folder = (process/'cwd').resolve()
            words = (process/'cmdline').read_bytes().decode().split('\0')
            if not any(word in ('scripts/run_studio.py', str(folder/'scripts/run_studio.py')) for word in words):
                continue
            if not (folder/'roundtable/static/studio.html').is_file():
                continue
            with urlopen('http://127.0.0.1:8765/api/meta', timeout=3) as response:
                meta = json.load(response)
            if meta.get('app_name') == 'UGC AI 圆桌' and {'host','planner','balance','engineer','audio','reviewer'} <= {r['id'] for r in meta.get('roles', [])}:
                return folder
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return None

def launch(args, name):
    RUN.mkdir(parents=True,exist_ok=True)
    with (RUN/(name+'.log')).open('ab') as output:
        process=subprocess.Popen(args,cwd=ROOT,stdin=subprocess.DEVNULL,stdout=output,stderr=output,start_new_session=True)
    return process.pid

def open_studio():
    url = 'http://127.0.0.1:8765/studio'
    if not (os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY')):
        print('当前无图形桌面，请在浏览器打开：' + url)
        return
    opener = shutil.which('xdg-open')
    if opener:
        launch([opener, url], 'browser')
    else:
        print('未找到 xdg-open，请手动打开：' + url)

def ensure_dependencies():
    """Bring up model and the project Gateway before declaring Studio ready."""
    try:
        from .deploy_spark import provision_model
    except ImportError:
        from deploy_spark import provision_model
    print('检查本机 Nemotron 模型…', flush=True)
    provision_model(3600)
    current = processes()
    if not current['gateway'] and not current['launcher']:
        with socket.socket() as probe:
            if probe.connect_ex(('127.0.0.1',19789)) == 0:
                raise RuntimeError('19789 被其他 Gateway 占用，未接管；请使用原项目入口。')
        launch([str(PYTHON),str(ROOT/'scripts/setup_local_openclaw.py'),'--start'],'gateway')
    print('[4/5 OpenClaw] 启动网关并校验连接…', flush=True)
    for _ in range(120):
        if processes()['gateway']:
            with socket.socket() as probe:
                if probe.connect_ex(('127.0.0.1',19789)) == 0:
                    try:
                        from .connection_probe import probe
                    except ImportError:
                        from connection_probe import probe
                    if not probe(ROOT)['openclaw']['ok']:
                        raise RuntimeError('OpenClaw 端口已打开，但项目 API 认证或模型列表检查失败；请查看连接检测与 Gateway 日志。')
                    print('本地模型与 OpenClaw 已连接（已核验 API 与认证）。', flush=True)
                    return
        time.sleep(.5)
    raise RuntimeError('项目 Gateway 未就绪，请查看 data/runtime/gateway.log')


def start(simulation=False, browser=True):
    try:
        from .connection_probe import probe, describe
    except ImportError:
        from connection_probe import probe, describe
    report=probe(ROOT)
    RUN.mkdir(parents=True,exist_ok=True)
    (RUN/'preflight.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print('[1/5 检测] 本机环境：\n'+'\n'.join(describe(report)),flush=True)
    current=processes()
    if current['studio']:
        if not health(): raise RuntimeError('项目进程存在但服务未就绪，请查看 data/runtime/studio.log')
        if not simulation: ensure_dependencies()
        print('SparkCraft 已运行：http://127.0.0.1:8765/studio')
        if browser: open_studio()
        return
    if health():
        existing = existing_studio_root()
        if existing:
            print('检测到另一目录的 SparkCraft 已运行，打开现有工作台：' + str(existing))
            print('本次使用上述目录的数据；没有启动便携目录的新实例。')
            print('如需独立运行当前目录，请先结束上述目录的服务，再在当前目录执行一键部署。')
            command = [sys.executable, str(existing/'scripts/linux_studio.py'), 'start']
            if not browser: command.append('--no-browser')
            if simulation: command.append('--simulation')
            subprocess.run(command, cwd=existing, check=True)
            return
        raise RuntimeError('8765 已被无法确认身份的服务占用，未接管。请检查端口。')
    if not PYTHON.exists():
        if simulation: raise RuntimeError("模拟模式请先创建 .venv 并安装 requirements.txt")
        print('首次运行：准备本地依赖、OpenClaw 和 Nemotron。需要联网，模型下载可能较大。', flush=True)
        command = [sys.executable, str(ROOT/'scripts/deploy_spark.py')]
        if not browser: command.append('--no-browser')
        # Release the launcher lock before installer launches this entry again.
        os.execv(sys.executable, command)
    if not simulation: ensure_dependencies()
    print('[5/5 工作台] 启动 Web 服务并打开浏览器',flush=True)
    args=[str(PYTHON),str(ROOT/'scripts/run_studio.py')]
    if simulation: args.append('--simulation')
    pid=launch(args,'studio')
    for _ in range(30):
        if health() and pid in processes()['studio']:
            print('SparkCraft 已启动：http://127.0.0.1:8765/studio')
            if browser: open_studio()
            return
        time.sleep(.5)
    raise RuntimeError('启动未就绪，请查看 data/runtime/studio.log')

def stop():
    # Recheck ownership immediately before each signal; never use pkill/name-only matching.
    for kind in ('startup','monitor','studio','gateway','launcher'):
        for pid in processes()[kind]:
            try: os.kill(pid,signal.SIGTERM)
            except ProcessLookupError: pass
        for _ in range(20):
            if not processes()[kind]: break
            time.sleep(.25)
    remaining=processes()
    if any(remaining.values()): raise RuntimeError('部分进程仍在退出，未强制结束。请稍后查看状态。')
    print('本项目 Studio、专用 Gateway 和监控已结束。vLLM 与其他 OpenClaw 实例不受影响。')

def monitor():
    if processes()['monitor']:
        print('后台监控已运行。'); return
    pid=launch([sys.executable,str(SCRIPT),'watch'],'monitor')
    print(f'后台监控已启动（PID {pid}）。日志：{RUN / "monitor.log"}')

def watch():
    lock=(RUN/'monitor.lock').open('a')
    try: fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError: return
    while True:
        state={'time':time.strftime('%Y-%m-%d %H:%M:%S'),'healthy':health(),'processes':processes()}
        temp=RUN/'health.tmp'; temp.write_text(json.dumps(state,ensure_ascii=False)); temp.replace(RUN/'health.json')
        print(json.dumps(state,ensure_ascii=False),flush=True)
        if (RUN/'monitor.log').stat().st_size > 5_000_000:
            # Keep the same file inode used by stdout while bounding long-running logs.
            with (RUN/'monitor.log').open('w'): pass
        time.sleep(15)

def background_start(simulation=False, browser=True):
    """Detach the complete bootstrap, so closing a terminal cannot cancel later stages."""
    RUN.mkdir(parents=True, exist_ok=True)
    with (RUN/'bootstrap.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        pid_file = RUN/'startup-worker.pid'
        if pid_file.exists():
            try:
                pid = int(pid_file.read_text())
                words = (Path('/proc')/str(pid)/'cmdline').read_bytes().split(b'\0')
                if (str(SCRIPT).encode() in words and b'--background-worker' in words) or str(ROOT/'scripts/deploy_spark.py').encode() in words:
                    print('后台启动仍在进行，请勿重复部署。日志：'+str(RUN/'startup.log'), flush=True)
                    return
            except (OSError, ValueError):
                pass
        command = [sys.executable, '-u', str(SCRIPT), 'start', '--background-worker']
        if simulation: command.append('--simulation')
        if not browser: command.append('--no-browser')
        log = RUN/'startup.log'
        (RUN/'startup-offset').write_text(str(log.stat().st_size if log.exists() else 0))
        pid = launch(command, 'startup')
        pid_file.write_text(str(pid))
    print(f'后台启动已开始（PID {pid}），关闭本窗口不会中断。', flush=True)
    print('顺序：加载本地模型 → 启动专用 OpenClaw → 打开工作台。', flush=True)
    print('首次部署与模型加载需要时间。日志：'+str(RUN/'startup.log'), flush=True)


def follow_startup():
    """Display detached worker progress; closing this viewer leaves startup running."""
    log = RUN/'startup.log'
    try:
        offset = int((RUN/'startup-offset').read_text())
    except (OSError, ValueError):
        offset = max(0, log.stat().st_size - 4096) if log.exists() else 0
    print('正在检测并启动，请等待。关闭窗口不会取消后台启动。', flush=True)
    while True:
        if log.exists():
            with log.open('rb') as stream:
                stream.seek(offset)
                chunk = stream.read()
                offset = stream.tell()
            if chunk:
                print(chunk.decode('utf-8', errors='replace'), end='', flush=True)
        try:
            pid = int((RUN/'startup-worker.pid').read_text())
            proc = Path('/proc')/str(pid)
            words = (proc/'cmdline').read_bytes().split(b'\0')
            alive = ((str(SCRIPT).encode() in words and b'--background-worker' in words)
                     or str(ROOT/'scripts/deploy_spark.py').encode() in words)
        except (OSError, ValueError):
            alive = False
        if not alive:
            # Drain the final message emitted immediately before worker exit.
            if log.exists() and log.stat().st_size > offset:
                continue
            recent = log.read_bytes()[int((RUN/'startup-offset').read_text()) if (RUN/'startup-offset').exists() else 0:] if log.exists() else b''
            if health() and ('SparkCraft 已启动' in recent.decode(errors='replace') or 'SparkCraft 已运行' in recent.decode(errors='replace')):
                print('[完成 ✓] 启动进度 5/5。若浏览器未自动打开，请访问 http://127.0.0.1:8765/studio', flush=True)
                return
            raise RuntimeError('启动未完成，请查看上方错误。完整日志：'+str(log))
        time.sleep(.5)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['start','start-background','follow-startup','stop','monitor','watch','status'])
    parser.add_argument('--background-worker', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--simulation',action='store_true')
    parser.add_argument('--no-browser',action='store_true')
    args=parser.parse_args(); os.chdir(ROOT); RUN.mkdir(parents=True,exist_ok=True)
    if args.action=='start-background': background_start(args.simulation, not args.no_browser); return
    if args.action=='follow-startup': follow_startup(); return
    if args.action=='watch': watch(); return
    with (RUN/'manager.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        if args.action=='start':
            print(time.strftime('%Y-%m-%d %H:%M:%S')+' 启动目录：'+str(ROOT), flush=True)
            start(args.simulation, not args.no_browser)
        elif args.action=='stop': stop()
        elif args.action=='monitor': monitor()
        else: print(json.dumps({'healthy':health(),'processes':processes()},ensure_ascii=False))

if __name__=='__main__':
    try: main()
    except (RuntimeError,OSError,subprocess.CalledProcessError) as error:
        print(str(error),file=sys.stderr); sys.exit(1)
