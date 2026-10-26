"""Verify the controlled A/B and quantify only pixel differences, not art quality."""
import hashlib
import json
from pathlib import Path
import numpy as np
from PIL import Image

root = Path(__file__).resolve().parent
baseline = json.loads((root / 'baseline.json').read_text())
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
assert sha(root / 'godot/assets/cat-cutout-v001.png') == baseline['texture_sha256']
assert sha(root / 'godot/models/room_v7.glb') == baseline['room_sha256']
assert sha(root / 'godot/profile.json') == baseline['profile_sha256']
captures = json.loads((root / 'shadow-check.json').read_text())['captures']
result = {'source_texture_room_profile_unchanged': True, 'views': {}}
for index, view in enumerate(['close', 'overview', 'bed-front']):
    a, b = captures[index * 2:index * 2 + 2]
    differing = [key for key in a if a[key] != b[key]]
    assert sorted(differing) == ['contact_shadow_visible', 'file'], differing
    x = np.asarray(Image.open(root / 'evidence' / a['file']).convert('RGB')).astype(np.int16)
    y = np.asarray(Image.open(root / 'evidence' / b['file']).convert('RGB')).astype(np.int16)
    delta = np.abs(x - y)
    changed = delta.max(axis=2) > 2
    rows, cols = np.where(changed)
    result['views'][view] = {
        'only_recorded_property_changed': 'contact_shadow_visible',
        'pixels_changed_gt2': int(changed.sum()),
        'max_channel_delta': int(delta.max()),
        'mean_absolute_channel_delta_changed_pixels': float(delta[changed].mean()) if changed.any() else 0,
        'difference_bbox': [int(cols.min()), int(rows.min()), int(cols.max() + 1), int(rows.max() + 1)] if changed.any() else None,
        'mean_signed_RGB_delta_changed_pixels': (y[changed] - x[changed]).mean(axis=0).tolist() if changed.any() else [],
        'max_positive_RGB_delta': int((y - x).max()),
    }
    assert int((y - x).max()) <= 1, 'Shadow must not brighten receiver channels'
    # Baseline replay must match the accepted previous render bit-for-bit.
    parent_name = {'close': '02-close.png', 'overview': '01-overview.png', 'bed-front': '03-bed-front.png'}[view]
    parent = np.asarray(Image.open(root.parent / '33-sprite-static/evidence' / parent_name).convert('RGB')).astype(np.int16)
    result['views'][view]['baseline_replay_max_pixel_delta'] = int(np.max(np.abs(parent - x)))
    assert np.array_equal(parent, x)
result['caveat'] = 'These are rendering differences, not an identity/style improvement score.'
(root / 'ab-check.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result, indent=2))
