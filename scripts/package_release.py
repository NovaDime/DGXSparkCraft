"""Build a clean source-portable release without local data or Git history."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
import zipfile
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from roundtable.config import Settings
from roundtable.export_safety import check_export
ALLOWED={'roundtable','scripts','skills','knowledge','tests','examples','docs','compat','.vscode'}
FILES={'README.md','项目说明与使用手册.md','requirements.txt','.env.example','.gitignore','启动.sh','结束.sh','后台监控.sh','一键部署.sh','安装桌面快捷方式.sh'}
SKIP={'__pycache__','.pytest_cache','.git','.venv','.runtime','data','node_modules'}

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    output=args.output.resolve()
    if output.exists() or Path(str(output)+'.zip').exists(): raise SystemExit('目标已存在，未覆盖')
    if output.is_relative_to(ROOT): raise SystemExit('发布目录必须在项目之外')
    settings=Settings.from_env(ROOT/'data/openclaw/roundtable.env')
    members=[]
    for path in sorted(ROOT.rglob('*')):
        rel=path.relative_to(ROOT)
        if rel.parts[0] not in ALLOWED and rel.as_posix() not in FILES:continue
        if any(x in SKIP for x in rel.parts) or path.is_symlink() or not path.is_file() or path.suffix in {'.pyc','.desktop'}:continue
        payload=path.read_bytes();check_export(settings,[payload]);members.append((path,rel,payload))
    output.mkdir(parents=True)
    manifest={}
    for path,rel,payload in members:
        target=output/rel;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,target)
        manifest[rel.as_posix()]=hashlib.sha256(payload).hexdigest()
    (output/'RELEASE-MANIFEST.json').write_text(
        json.dumps(
            {
                'version':'1.1.0',
                'files':manifest,
                'excluded':['credentials','user data','git history','web archives','installed runtimes','model weights'],
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
