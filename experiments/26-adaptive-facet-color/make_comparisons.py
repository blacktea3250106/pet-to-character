"""Assemble labeled actual-render comparisons. No retouching or generated imagery."""
from pathlib import Path
import hashlib
import json
from PIL import Image, ImageDraw, ImageFont

P = Path(__file__).resolve().parent
font = ImageFont.truetype('/System/Library/Fonts/Helvetica.ttc', 30)
small = ImageFont.truetype('/System/Library/Fonts/Helvetica.ttc', 22)
baseline = P.parent / '25-appearance-diagnostic/matte-candidate/preview'
cases = [('Baseline', baseline),
         ('A: adaptive facets / 18', P / 'results-v001/delta18/preview'),
         ('B: adaptive facets / 28', P / 'results-v001/delta28/preview')]
evidence = []


def add(canvas, source, xy, size):
    with Image.open(source) as im:
        canvas.paste(im.convert('RGB').resize(size, Image.Resampling.LANCZOS), xy)
    evidence.append({'path': str(source), 'sha256': hashlib.sha256(source.read_bytes()).hexdigest()})


canvas = Image.new('RGB', (2304, 1688), '#f4f3ef')
draw = ImageDraw.Draw(canvas)
draw.text((24, 18), 'ACTUAL 3D RENDERS  |  3,500 triangles  |  Same geometry, camera, lights and material settings', font=font, fill='#20242a')
for col, (label, folder) in enumerate(cases):
    draw.text((col * 768 + 24, 68), label, font=font, fill='#20242a')
    for row, az in enumerate(['315', '045']):
        add(canvas, folder / f'original-az{az}-el12.png', (col * 768, 112 + row * 768), (768, 768))
draw.text((24, 1650), 'Only base-color processing differs. These candidates are not final identity/style/animation acceptance.', font=small, fill='#41464c')
canvas.save(P / 'comparison-all.png')

canvas = Image.new('RGB', (2048, 1100), '#f4f3ef')
draw = ImageDraw.Draw(canvas)
for col, (label, folder) in enumerate([cases[0], cases[2]]):
    draw.text((col * 1024 + 24, 16), label + ' | 3,500 triangles', font=font, fill='#20242a')
    add(canvas, folder / 'original-az315-el12.png', (col * 1024, 64), (1024, 1024))
canvas.save(P / 'comparison-before-after.png')

detail = P / 'detail-v001'
if (detail / 'report.json').exists():
    canvas = Image.new('RGB', (2304, 2432), '#f4f3ef')
    draw = ImageDraw.Draw(canvas)
    draw.text((24, 18), 'ACTUAL GLB FACE DETAILS  |  Same framing and lighting; texture processing only', font=font, fill='#20242a')
    for col, (name, label) in enumerate([('baseline', 'Baseline'), ('delta18', 'A: adaptive facets / 18'), ('delta28', 'B: adaptive facets / 28')]):
        draw.text((col * 768 + 24, 66), label, font=font, fill='#20242a')
        for row, az in enumerate(['315', '000', '045']):
            add(canvas, detail / f'{name}-az{az}.png', (col * 768, 112 + row * 768), (768, 768))
    canvas.save(P / 'comparison-face.png')
(P / 'comparison-provenance.json').write_text(json.dumps({'processing': 'Labeled layout and uniform resizing only; no repainting', 'source_images': evidence}, indent=2) + '\n')
