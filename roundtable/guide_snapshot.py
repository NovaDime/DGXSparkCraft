"""Reproducible full-text guide cache; never label a repository snapshot as live official HTML."""
import asyncio
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from urllib.parse import quote
import httpx

REPOSITORY = 'MCNeteaseDevs/netease-bedrock-wiki'
REVISION = '894160bb5849e0b3c2be8d46351ca6e49f812fc8'
API = f'https://api.github.com/repos/{REPOSITORY}/git/trees/{REVISION}?recursive=1'


def guide_paths(tree):
    if tree.get('truncated'):
        raise ValueError('目录被 GitHub 截断，不能标记完整')
    paths = []
    for item in tree.get('tree', []):
        path = item.get('path', '')
        parts = PurePosixPath(path).parts
        if item.get('type') == 'blob' and path.startswith('mcguide/') and path.endswith('.md'):
            if '..' in parts or '\\' in path or len(parts) < 2:
                raise ValueError('文档路径无效')
            paths.append(path)
    if not paths or len(paths) > 2000:
        raise ValueError('开发指南目录数量异常')
    return sorted(set(paths))


async def sync_guide(folder: Path, client=None):
    if client is None:
        async with httpx.AsyncClient(trust_env=False, timeout=30, follow_redirects=False) as owned:
            return await sync_guide(folder, owned)
    folder.mkdir(parents=True, exist_ok=True)
    response = await client.get(API, timeout=30)
    response.raise_for_status()
    paths = guide_paths(response.json())
    semaphore = asyncio.Semaphore(6)
    now = datetime.now(timezone.utc).isoformat()
    previous_path = folder.parent / (folder.name + '-manifest.json')
    previous = json.loads(previous_path.read_text()) if previous_path.exists() else {}
    old = {x['path']: x for x in previous.get('documents', [])} if previous.get('revision') == REVISION else {}

    async def fetch(path):
        relative = path.removeprefix('mcguide/')
        target = folder / 'guide' / relative
        url = f'https://raw.githubusercontent.com/{REPOSITORY}/{REVISION}/' + quote(path)
        official = 'https://mc.163.com/dev/mcmanual/mc-dev/' + quote(path[:-3] + '.html')
        if path in old and target.is_file() and hashlib.sha256(target.read_bytes()).hexdigest() == old[path]['sha256']:
            return old[path], None
        async with semaphore:
            for attempt in range(3):
                try:
                    async with client.stream('GET', url, timeout=30) as r:
                        r.raise_for_status()
                        data = bytearray()
                        async for chunk in r.aiter_bytes():
                            data.extend(chunk)
                            if len(data) > 900000:
                                raise ValueError('单篇正文超出限制')
                    body = bytes(data).decode('utf-8-sig')
                    content = (f'# 开发指南参考快照\n\n原始官方链接：{official}\n仓库来源：{url}\n固定版本：{REVISION}\n抓取时间：{now}\n'
                               '范围：原始 Markdown 正文完整保留；图片和视频仅保留原链接，未下载媒体。不是当前官网版本或游戏内验证结果。\n\n' + body)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    temp = target.with_suffix('.tmp'); temp.write_text(content, encoding='utf-8'); temp.replace(target)
                    return {'path': path, 'official_url': official, 'source_url': url, 'characters': len(body),
                            'empty': not bool(body.strip()), 'sha256': hashlib.sha256(target.read_bytes()).hexdigest()}, None
                except (httpx.HTTPError, ValueError, OSError, UnicodeError) as exc:
                    if attempt == 2:
                        return None, {'path': path, 'error': type(exc).__name__}
                    await asyncio.sleep(attempt + 1)
    results = await asyncio.gather(*(fetch(path) for path in paths))
    documents = [d for d, _ in results if d]
    failures = [e for _, e in results if e]
    report = {'repository': REPOSITORY, 'revision': REVISION, 'updated_at': now,
              'expected_count': len(paths), 'downloaded_count': len(documents),
              'document_count': sum(not d.get('empty', False) for d in documents),
              'empty_count': sum(d.get('empty', False) for d in documents),
              'character_count': sum(d['characters'] for d in documents),
              'status': 'guide_snapshot' if not failures else 'guide_snapshot_partial',
              'note': '开发指南仓库 Markdown 全文快照；非官网实时镜像，不含媒体文件。',
              'failures': failures, 'documents': documents}
    temp = previous_path.with_suffix('.tmp'); temp.write_text(json.dumps(report, ensure_ascii=False, indent=2)); temp.replace(previous_path)
    return {k: v for k, v in report.items() if k != 'documents'}
