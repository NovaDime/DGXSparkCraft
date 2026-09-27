#!/usr/bin/env python3
"""缓存网易开发指南全部 Markdown 正文并更新 Agent 检索索引。"""
import argparse
import asyncio
import json
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from roundtable.official_knowledge import OfficialKnowledge
from roundtable.guide_snapshot import sync_guide

async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, default=ROOT / 'data')
    args = parser.parse_args()
    knowledge = OfficialKnowledge(args.data_dir)
    try:
        report = await sync_guide(knowledge.source_root / 'guide')
        knowledge.meta['guide'] = report
        knowledge.refresh_index()
        temp = knowledge.meta_path.with_suffix('.tmp')
        temp.write_text(json.dumps(knowledge.meta, ensure_ascii=False, indent=2)); temp.replace(knowledge.meta_path)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        if report['failures']:
            raise SystemExit(1)
    finally:
        knowledge.close()
if __name__ == '__main__':
    asyncio.run(main())
