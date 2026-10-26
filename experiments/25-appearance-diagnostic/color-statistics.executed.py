"""Compare aligned diagnostic renders using geometry-derived interior pixels.

The bins describe displayed base-color brightness, not anatomical coat labels.
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

parser = argparse.ArgumentParser()
parser.add_argument('diagnostic', type=Path)
parser.add_argument('output', type=Path)
args = parser.parse_args()
report = json.loads((args.diagnostic / 'report.json').read_text())
if args.output.exists():
    raise RuntimeError('Do not replace a diagnostic result')
results = []
hashes = {}
for az in report['config']['views']:
    images = {}
    for mode in ('baseline', 'no_specular', 'base_color', 'alpha-source'):
        path = args.diagnostic / f'{mode}-az{az % 360:03d}.png'
        hashes[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
        images[mode] = np.asarray(Image.open(path).convert('RGBA'))
    if len({im.shape for im in images.values()}) != 1:
        raise ValueError('Diagnostic images must share resolution')
    raw_mask = (images['alpha-source'][:, :, 3] >= 254).astype(np.uint8) * 255
    # Two-pixel erosion removes silhouette anti-aliasing and mixed background.
    mask = np.asarray(Image.fromarray(raw_mask).filter(ImageFilter.MinFilter(5))) > 0
    if np.count_nonzero(mask) == 0:
        raise ValueError('No valid mesh interior')
    luma = {k: im[:, :, :3].astype(float) @ np.array([.2126, .7152, .0722])
            for k, im in images.items() if k != 'alpha-source'}
    bins = []
    for lo, hi in report['config']['luminance_groups_srgb_255']:
        selection = mask & (luma['base_color'] >= lo) & (luma['base_color'] < hi)
        n = int(np.count_nonzero(selection))
        if n == 0:
            continue
        stats = {}
        for mode in ('baseline', 'no_specular', 'base_color'):
            values = luma[mode][selection]
            stats[mode] = {'mean_luma_255': float(values.mean()),
                           'median_luma_255': float(np.median(values)),
                           'p10_luma_255': float(np.percentile(values, 10)),
                           'p90_luma_255': float(np.percentile(values, 90))}
        effect = (luma['baseline'] - luma['no_specular'])[selection]
        bins.append({'base_color_luma_range': [lo, hi], 'pixel_count': n,
                     'fraction_of_mesh_interior': n / int(mask.sum()), 'modes': stats,
                     'baseline_minus_no_specular_mean_luma_255': float(effect.mean()),
                     'baseline_minus_no_specular_p90_luma_255': float(np.percentile(effect, 90))})
    results.append({'azimuth': az, 'interior_pixels': int(mask.sum()), 'bins': bins})
output = {
    'source_sha256': report['source_sha256'],
    'diagnostic_report_sha256': hashlib.sha256((args.diagnostic / 'report.json').read_bytes()).hexdigest(),
    'images_sha256': hashes, 'views': results,
    'metric': 'Rec.709-weighted display sRGB luma on 0–255 scale; not linear physical luminance',
    'mask': 'Actual rendered model alpha >=254, eroded two pixels; no hand regions or semantic labels',
    'scope': 'Same-camera material-isolation diagnostics. Equal weight per visible pixel. Bins are based on unlit base color. Does not measure photo identity, cat.png similarity, texture sharpness or animation quality.',
    'quality_acceptance': False
}
args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n')
args.output.with_suffix('.executed.py').write_bytes(Path(__file__).read_bytes())
print(json.dumps({'views': len(results), 'interior_pixels': [v['interior_pixels'] for v in results], 'quality_acceptance': False}))
