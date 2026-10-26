"""Measure actual rendered ablations. Does not edit any source/evidence image."""
from pathlib import Path
import json
import numpy as np
from PIL import Image

root = Path(__file__).resolve().parent
report = {}
pairs = [
    ('shadow', '02-close.png', '02b-close-shadow-off-diagnostic.png'),
    ('depth_behind_no_projected_overlap', '04-bed-behind-depth-on.png', '05-bed-behind-depth-off-diagnostic.png'),
    ('depth_bed_edge', '07-bed-edge-depth-on.png', '08-bed-edge-depth-off-diagnostic.png'),
]
for key, a, b in pairs:
    x = np.array(Image.open(root / 'evidence' / a).convert('RGB')).astype('int16')
    y = np.array(Image.open(root / 'evidence' / b).convert('RGB')).astype('int16')
    difference = np.max(np.abs(x - y), axis=2)
    yy, xx = np.where(difference > 2)
    report[key] = {
        'changed_pixels_gt2': int((difference > 2).sum()),
        'max_channel_difference': int(difference.max()),
        'difference_bbox': [int(xx.min()), int(yy.min()), int(xx.max() + 1), int(yy.max() + 1)] if len(xx) else None,
        'files': [a, b],
        'meaning': 'Effect of the single rendering toggle, not a perceptual quality or identity score.',
    }
(root / 'render-differences.json').write_text(json.dumps(report, indent=2) + '\n')
assert report['shadow']['changed_pixels_gt2'] > 0
assert report['depth_bed_edge']['changed_pixels_gt2'] > 0
print(json.dumps(report, indent=2))
