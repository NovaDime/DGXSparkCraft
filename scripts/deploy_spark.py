"""Project-private DGX Spark deployment. --dry-run never changes files/services."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shlex
import socket
import subprocess
import sys
import tarfile
import tempfile
import time
from urllib.request import urlopen, urlretrieve

ROOT = Path(__file__).resolve().parent.parent
NODE = '26.7.0'
OPENCLAW = '2026.9.4'
IMAGE = 'vllm/vllm-openai:v0.27.1'
MODEL = 'nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-NVFP4'
ALIAS = 'nemotron-3.5-lightning'
ENDPOINT = 'http://127.0.0.1:8000/v1'

def run(command, **kwargs):
    print('+ ' + shlex.join(map(str, command)), flush=True)
    return subprocess.run(list(map(str, command)), check=True, cwd=ROOT, **kwargs)

def model_command():
    return ['docker', 'run', '-d', '--name', 'sparkcraft-nemotron-3-5', '--label', 'ai.sparkcraft.managed=nemotron', '--gpus', 'all', '--ipc=host',
            '-p', '127.0.0.1:8000:8000', '-v', str(Path.home()/'.cache/huggingface')+':/root/.cache/huggingface',
            IMAGE, '--model', MODEL, '--served-model-name', ALIAS, '--moe-backend', 'marlin',
            '--kv-cache-dtype', 'fp8', '--enable-prefix-caching', '--gpu-memory-utilization', '0.85',
            '--speculative_config.num_speculative_tokens', '3', '--mamba-backend', 'flashinfer',
            '--mamba-cache-mode', 'align', '--reasoning-parser', 'nemotron_v3',
            '--speculative_config.model', MODEL+'-DSpark', '--tool-call-parser', 'qwen3_coder', '--enable-auto-tool-choice']

def available_model():
    try:
        with urlopen(ENDPOINT+'/models', timeout=4) as response:
            ids = [item['id'] for item in json.load(response)['data']]
        for name in (ALIAS, MODEL):
            if name in ids: return name
        raise RuntimeError('8000 上已有模型服务，但不是指定 Nemotron；未覆盖。')
    except (OSError, ValueError, KeyError): return None

def provision_model(timeout):
    model = available_model()
    if model:
        print('复用本机 Nemotron：' + model)
        return model
    # Reuse the known local installation only after checking model, image and binding.
    legacy = subprocess.run(['docker', 'inspect', 'nemotron-3.5-lightning'], capture_output=True, text=True)
    if legacy.returncode == 0:
        item = json.loads(legacy.stdout)[0]
        config = item.get('Config', {})
        bindings = item.get('HostConfig', {}).get('PortBindings', {}).get('8000/tcp', [])
        if config.get('Image') == IMAGE and MODEL in config.get('Cmd', []) and any(b.get('HostIp') == '127.0.0.1' and b.get('HostPort') == '8000' for b in bindings):
            if not item['State']['Running']:
                with socket.socket() as probe:
                    if probe.connect_ex(('127.0.0.1',8000)) == 0: raise RuntimeError('模型端口被占用，未启动原容器')
                busy = run(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader'],capture_output=True,text=True)
                if busy.stdout.strip(): raise RuntimeError('GPU 已被其他计算任务使用，未启动原容器')
                run(['docker','start','nemotron-3.5-lightning'])
            print('等待已有 Nemotron 容器加载，复用原权重缓存。',flush=True)
            deadline=time.monotonic()+timeout
            while time.monotonic()<deadline:
                model=available_model()
                if model:return model
                time.sleep(5)
            raise RuntimeError('原模型容器尚未就绪，请检查 docker logs nemotron-3.5-lightning')
    # Only resume a container whose explicit label and model match this installer.
    inspection = subprocess.run(['docker', 'inspect', 'sparkcraft-nemotron-3-5'], capture_output=True, text=True)
    managed = None
    if inspection.returncode == 0:
        managed = json.loads(inspection.stdout)[0]
        config = managed.get('Config', {})
        if config.get('Labels', {}).get('ai.sparkcraft.managed') != 'nemotron' or MODEL not in config.get('Cmd', []):
            raise RuntimeError('同名模型容器不是本部署器管理的实例，未启动或覆盖。')
    if not managed or not managed['State']['Running']:
        with socket.socket() as probe:
            if probe.connect_ex(('127.0.0.1', 8000)) == 0:
                raise RuntimeError('8000 已被占用但模型 API 不可用；未启动新模型。')
        result = run(['nvidia-smi', '--query-compute-apps=pid', '--format=csv,noheader'], capture_output=True, text=True)
        if result.stdout.strip():
            raise RuntimeError('GPU 已有计算进程；未启动额外模型以避免影响现有任务。')
        run(['docker', 'info'], stdout=subprocess.DEVNULL)
        if managed:
            run(['docker', 'start', 'sparkcraft-nemotron-3-5'])
        else:
            run(model_command())
    print('等待 Nemotron 模型接口就绪；首次下载或加载可能较久。', flush=True)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        model = available_model()
        if model: return model
        state = subprocess.run(['docker', 'inspect', '--format', '{{.State.Status}}', 'sparkcraft-nemotron-3-5'], capture_output=True, text=True)
        if state.returncode == 0 and state.stdout.strip() in {'exited','dead'}:
            raise RuntimeError('模型容器已停止，请检查 docker logs sparkcraft-nemotron-3-5；未无限等待。')
        time.sleep(5)
    raise RuntimeError('模型尚未就绪（首次下载较慢）。查看 docker logs sparkcraft-nemotron-3-5，等待后重新部署；未停止容器。')

def install_node():
    dest = ROOT/'.runtime/node'
    executable = dest/'bin/node'
    if executable.exists():
        version = run([executable, '--version'], capture_output=True, text=True).stdout.strip()
        if version != 'v'+NODE: raise RuntimeError('项目 Node 版本不符，未覆盖：'+version)
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    archive = 'node-v'+NODE+'-linux-arm64.tar.xz'
    base = 'https://nodejs.org/dist/v'+NODE+'/'
    with tempfile.TemporaryDirectory(dir=dest.parent) as directory:
        temporary = Path(directory)
        urlretrieve(base+archive, temporary/archive)
        with urlopen(base+'SHASUMS256.txt', timeout=60) as response:
            lines = response.read().decode().splitlines()
        expected = next(line.split()[0] for line in lines if line.split()[-1] == archive)
        actual = hashlib.sha256((temporary/archive).read_bytes()).hexdigest()
        if actual != expected: raise RuntimeError('Node SHA256 校验失败')
        with tarfile.open(temporary/archive) as bundle: bundle.extractall(temporary, filter='data')
        (temporary/archive.removesuffix('.tar.xz')).rename(dest)

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--no-browser', action='store_true')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--model-timeout', type=int, default=3600)
    args = parser.parse_args(argv)
    if args.dry_run:
        print('DRY RUN：不下载、不写配置、不安装、不启动任何服务。')
        print(f'Linux ARM64 / Python >=3.12 / Node {NODE} / OpenClaw {OPENCLAW} / {IMAGE}')
        print('先探测 '+ENDPOINT+'/models；匹配则复用。端口占用或 GPU 忙则退出。空闲时才运行：')
        print(shlex.join(model_command()))
        print('校验 Node SHA256；安装至 .runtime/node；OpenClaw 安装至 .runtime/openclaw；Python 安装至 .venv。')
        print('创建项目配置 data/openclaw（19789）；生成当前位置桌面入口；启动 Studio 并打开 /studio。')
        return
    if platform.system() != 'Linux' or platform.machine() not in ('aarch64', 'arm64'):
        raise RuntimeError('此部署入口仅支持 DGX Spark Linux ARM64。')
    if sys.version_info < (3,12): raise RuntimeError('需要 Python 3.12+（含 venv）。')
    model = provision_model(args.model_timeout)
    install_node()
    env = {**os.environ, 'PATH': str(ROOT/'.runtime/node/bin')+os.pathsep+os.environ.get('PATH','')}
    prefix = ROOT/'.runtime/openclaw'
    package = prefix/'lib/node_modules/openclaw/package.json'
    if not package.exists():
        run([ROOT/'.runtime/node/bin/npm', 'install', '-g', '--prefix', prefix, 'openclaw@'+OPENCLAW], env=env)
    elif json.loads(package.read_text())['version'] != OPENCLAW:
        raise RuntimeError('项目 OpenClaw 版本不符，未覆盖。')
    python = ROOT/'.venv/bin/python'
    if not python.exists(): run([sys.executable, '-m', 'venv', ROOT/'.venv'])
    run([python, '-m', 'pip', 'install', '-r', ROOT/'requirements.txt'])
    run([python, ROOT/'scripts/setup_local_openclaw.py', '--model', model], env=env)
    run([sys.executable, ROOT/'scripts/install_desktop.py'])
    run([sys.executable, ROOT/'scripts/linux_studio.py', 'start'] + (['--no-browser'] if args.no_browser else []), env=env)

if __name__ == '__main__':
    try: main()
    except (RuntimeError, OSError, subprocess.CalledProcessError) as error:
        print('部署未完成：'+str(error), file=sys.stderr)
        sys.exit(1)
