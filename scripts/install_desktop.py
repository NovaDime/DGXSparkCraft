"""Generate launchers for this extracted location; rerun after moving the folder."""
from pathlib import Path
import os
import subprocess
ROOT = Path(__file__).resolve().parent.parent

def quoted(value):
    # Desktop Entry Exec quoting, including its separate percent expansion.
    return '"' + str(value).replace('\\', '\\\\').replace('"', '\\"').replace('`', '\\`').replace('$', '\\$').replace('%', '%%') + '"'

def main():
    desktop = Path.home() / 'Desktop'
    try:
        result = subprocess.run(['xdg-user-dir', 'DESKTOP'], capture_output=True, text=True, check=True)
        if result.stdout.strip(): desktop = Path(result.stdout.strip())
    except (OSError, subprocess.CalledProcessError): pass
    targets = [ROOT, Path(os.environ.get('XDG_DATA_HOME', str(Path.home()/'.local/share'))) / 'applications']
    if desktop.is_dir() and desktop != Path.home(): targets.append(desktop)
    for target in targets:
        target.mkdir(parents=True, exist_ok=True)
        for name, script in [('SparkCraft', '启动.sh'), ('SparkCraft-Deploy', '一键部署.sh')]:
            path = target / (name + '.desktop')
            path.write_text('[Desktop Entry]\nType=Application\nVersion=1.0\nName=' + ('SparkCraft 创作工作室' if name == 'SparkCraft' else 'SparkCraft 一键部署') + '\nExec=/bin/bash ' + quoted(ROOT/script) + '\nTerminal=true\nIcon=applications-games\nCategories=Development;\n', encoding='utf-8')
            path.chmod(0o755)
            try: subprocess.run(['gio', 'set', str(path), 'metadata::trusted', 'true'], capture_output=True)
            except OSError: pass
            print('快捷方式：' + str(path))
if __name__ == '__main__': main()
