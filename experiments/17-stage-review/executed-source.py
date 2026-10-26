"""Render an evidence manifest into a marked section of an existing workflow.

This validates provenance and presentation, not identity, anatomy or art quality.
No images/models are modified. Requires Pillow for full image decoding.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
from urllib.parse import quote
from PIL import Image

START = '<!-- stage-review:start -->'
END = '<!-- stage-review:end -->'
KINDS = {'photo': '真實照片', 'photo_diagnostic': '原照處理／標註',
         'ai_reference': 'AI 2D 參考圖', 'render': '真實 3D 渲染',
         'diagnostic': '程序診斷圖'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest', type=Path)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--document', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--write', action='store_true', help='Update only the marked document section')
    args = parser.parse_args()
    root = args.root.resolve()
    document = args.document.resolve()
    if not document.is_relative_to(root):
        raise ValueError('Document must belong to the workspace')
    data = json.loads(args.manifest.read_text())
    stages = data['stages']
    if [s['id'] for s in stages] != [f'P{i:02}' for i in range(10)]:
        raise ValueError('Expected an ordered P00–P09 evidence record')
    files = {}

    def inspect(item, picture=False):
        path = (root / item['path']).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise ValueError(f'Missing or outside workspace: {item["path"]}')
        raw = path.read_bytes()
        entry = {'path': item['path'], 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
        if picture:
            if item['kind'] not in KINDS:
                raise ValueError('Every image needs an explicit provenance type')
            with Image.open(path) as im:
                im.load()
                entry['image_size'] = list(im.size)
            entry['kind'] = item['kind']
        files[item['path']] = entry
        return quote(os.path.relpath(path, document.parent), safe='/.-_')

    lines = [START, '', data['heading'], '', data['summary'], '']
    for stage in stages:
        for key in ('title', 'status', 'result', 'manual_dependency', 'remaining'):
            if not stage[key]:
                raise ValueError(f'{stage["id"]}: missing {key}')
        if not stage['images'] or not stage['evidence']:
            raise ValueError('Each completed research stage needs visible output and evidence')
        lines.extend([f'### {stage["id"]} · {stage["title"]}', '',
                      f'**狀態：{stage["status"]}。** {stage["result"]}', '',
                      f'人工依賴：{stage["manual_dependency"]}', '',
                      f'未通過／限制：{stage["remaining"]}', ''])
        for picture in stage['images']:
            href = inspect(picture, True)
            label = f'{KINDS[picture["kind"]]}｜{picture["label"]}'
            lines.extend([f'![{label}]({href})', '', label, ''])
        links = [f'[{item["label"]}]({inspect(item)})' for item in stage['evidence']]
        lines.extend(['證據與檔案：' + ' · '.join(links), ''])
    lines.extend([data['conclusion'], '', END])
    block = '\n'.join(lines)
    existing = document.read_text()
    if START in existing or END in existing:
        if existing.count(START) != 1 or existing.count(END) != 1 or existing.index(END) < existing.index(START):
            raise ValueError('Ambiguous generated section markers')
        updated = existing[:existing.index(START)] + block + existing[existing.index(END) + len(END):]
    else:
        updated = existing.rstrip() + '\n\n' + block + '\n'
    if args.write:
        document.write_text(updated)
    report = {'schema_version': 1, 'case_id': data['case_id'], 'stage_count': len(stages),
              'file_count': len(files), 'files': sorted(files.values(), key=lambda f: f['path']),
              'manifest_sha256': hashlib.sha256(args.manifest.read_bytes()).hexdigest(),
              'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'document_matches_manifest': (document.read_text() == updated),
              'all_images_decoded': True, 'quality_acceptance': False,
              'scope': 'Evidence links, hashes and presentation only; manual review statements are not automatically certified'}
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: report[k] for k in ['stage_count', 'file_count', 'document_matches_manifest', 'all_images_decoded', 'quality_acceptance']}))
    if not report['document_matches_manifest']:
        raise SystemExit('Stage section is stale; inspect changes before regenerating with --write')


if __name__ == '__main__':
    main()
