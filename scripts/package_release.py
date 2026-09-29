"""Build a clean source-portable release without local data or Git history."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
import zipfile
import re
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from roundtable.config import Settings
from roundtable.export_safety import check_export
ALLOWED={'roundtable','scripts','skills','knowledge','tests','examples','docs','compat','.vscode'}
FILES={'README.md','项目说明与使用手册.md','requirements.txt','.env.example','.gitignore','启动.sh','结束.sh','后台监控.sh','一键部署.sh','安装桌面快捷方式.sh'}
SKIP={'__pycache__','.pytest_cache','.git','.venv','.runtime','data','node_modules'}
GITHUB_SKIP = {'tests', 'examples', 'compat', 'evals'}
GITHUB_FILES = {'docs/local-validation.md', 'docs/studio-validation.md', 'docs/发布验收记录.md',
                'docs/competition-demo.md', 'docs/hackathon-alignment.md', 'scripts/verify_local.py',
                'scripts/manage.ps1', 'scripts/service.py'}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--version',default='1.2.0')
    parser.add_argument('--github',action='store_true',help='Exclude development fixtures, historical validation records and Windows entry points')
    args=parser.parse_args()
    if not re.fullmatch(r'\d+\.\d+\.\d+', args.version): parser.error('版本应为 major.minor.patch')
    output=args.output.resolve()
    if output.exists() or Path(str(output)+'.zip').exists(): raise SystemExit('目标已存在，未覆盖')
    if output.is_relative_to(ROOT): raise SystemExit('发布目录必须在项目之外')
    settings=Settings.from_env(ROOT/'data/openclaw/roundtable.env')
    members=[]
    for path in sorted(ROOT.rglob('*')):
        rel=path.relative_to(ROOT)
        if rel.parts[0] not in ALLOWED and rel.as_posix() not in FILES:continue
        if any(x in SKIP for x in rel.parts) or path.is_symlink() or not path.is_file() or path.suffix in {'.pyc','.desktop'}:continue
        if args.github and (any(x in GITHUB_SKIP for x in rel.parts) or rel.as_posix() in GITHUB_FILES or path.name == 'BENCHMARK.md'):continue
        payload=path.read_bytes();check_export(settings,[payload]);members.append((path,rel,payload))
    output.mkdir(parents=True)
    manifest={}
    for path,rel,payload in members:
        target=output/rel;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,target)
        manifest[rel.as_posix()]=hashlib.sha256(payload).hexdigest()
    (output/'RELEASE-MANIFEST.json').write_text(
        json.dumps(
            {
                'version':args.version,
                'files':manifest,
                'excluded':['credentials','user data','git history','web archives','installed runtimes','model weights'] + (['tests','examples','historical validation records','Windows entry points','skill evals'] if args.github else []),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding='utf-8',
    )
    archive=Path(str(output)+'.zip')
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
        for path in sorted(output.rglob('*')):
            if path.is_file():z.write(path,Path(output.name)/path.relative_to(output))
    print(json.dumps({'directory':str(output),'archive':str(archive),'files':len(manifest),'sha256':hashlib.sha256(archive.read_bytes()).hexdigest()},ensure_ascii=False))
if __name__=='__main__':main()
