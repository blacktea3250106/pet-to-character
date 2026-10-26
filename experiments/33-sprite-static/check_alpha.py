"""Read-only PNG checks. Never edits or repairs image pixels."""
import argparse
import json
from pathlib import Path
import numpy as np
from PIL import Image
from scipy import ndimage

parser = argparse.ArgumentParser()
parser.add_argument('image', type=Path)
parser.add_argument('output', type=Path)
args = parser.parse_args()
im = Image.open(args.image)
a = np.array(im.getchannel('A')) if 'A' in im.getbands() else np.full((im.height, im.width), 255, dtype=np.uint8)
mask = a >= 128
labels, count = ndimage.label(mask)
sizes = np.bincount(labels.ravel())
sizes[0] = 0
report = {
    'file': str(args.image), 'mode': im.mode, 'size': list(im.size),
    'alpha_range': [int(a.min()), int(a.max())],
    'transparent_fraction': float(np.mean(a == 0)),
    'semitransparent_fraction': float(np.mean((a > 0) & (a < 255))),
    'alpha128_bbox': Image.fromarray(mask.astype('uint8') * 255).getbbox(),
    'opaque_border_pixel_count': int(mask[0,:].sum() + mask[-1,:].sum() + mask[:,0].sum() + mask[:,-1].sum()),
    'connected_components_alpha128': count,
    'largest_component_pixels': int(sizes.max()),
    'pixels_outside_largest_component': int(mask.sum() - sizes.max()),
    'component_areas_largest10': sorted([int(s) for s in sizes if s], reverse=True)[:10],
    'semantic_identity_and_grounding_pass': 'not_decided_by_alpha_statistics',
}
args.output.write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))
