"""Linux project-scoped start/stop/monitor; never manages vLLM or foreign gateways."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parent.parent
RUN = ROOT / "data" / "runtime"
PYTHON = ROOT / ".venv" / "bin" / "python"
SCRIPT = Path(__file__).resolve()

def processes():
    found = {"studio": [], "gateway": [], "launcher": [], "monitor": []}
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

def start(simulation=False, browser=True):
    current=processes()
    if current['studio']:
        if not health(): raise RuntimeError('项目进程存在但服务未就绪，请查看 data/runtime/studio.log')
        print('SparkCraft 已运行：http://127.0.0.1:8765/studio')
        if browser: open_studio()
        return
    if health(): raise RuntimeError('8765 已有其他服务，未接管。请检查端口。')
    if not PYTHON.exists(): raise RuntimeError('请先执行：python3 -m venv .venv，然后 .venv/bin/pip install -r requirements.txt')
    if not simulation and not current['gateway']:
        if current['launcher']: raise RuntimeError('项目 Gateway 正在启动，请稍后重试。')
        launch([str(PYTHON),str(ROOT/'scripts/setup_local_openclaw.py'),'--start'],'gateway')
        for _ in range(20):
            if processes()['gateway']: break
            time.sleep(.5)
        else: raise RuntimeError('项目 Gateway 未启动，请查看 data/runtime/gateway.log')
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
    for kind in ('monitor','studio','gateway','launcher'):
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

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['start','stop','monitor','watch','status'])
    parser.add_argument('--simulation',action='store_true')
    parser.add_argument('--no-browser',action='store_true')
    args=parser.parse_args(); os.chdir(ROOT); RUN.mkdir(parents=True,exist_ok=True)
    if args.action=='watch': watch(); return
    with (RUN/'manager.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        if args.action=='start': start(args.simulation, not args.no_browser)
        elif args.action=='stop': stop()
        elif args.action=='monitor': monitor()
        else: print(json.dumps({'healthy':health(),'processes':processes()},ensure_ascii=False))

if __name__=='__main__':
    try: main()
    except (RuntimeError,OSError) as error:
        print(str(error),file=sys.stderr); sys.exit(1)
