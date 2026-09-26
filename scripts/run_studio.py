"""Launch the studio using project-local OpenClaw config, or explicit simulation."""
import argparse
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import uvicorn
from roundtable.config import Settings
from roundtable.app import create_app

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--simulation', action='store_true')
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    settings = Settings() if args.simulation else Settings.from_env(ROOT / 'data/openclaw/roundtable.env')
    if not args.simulation and settings.provider_mode != 'openclaw':
        parser.error('先运行 scripts/setup_local_openclaw.py --start；离线演示请显式选择 --simulation')
    uvicorn.run(create_app(settings), host='127.0.0.1', port=args.port, workers=1)
