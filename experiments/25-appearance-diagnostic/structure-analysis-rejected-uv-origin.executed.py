"""Read-only diagnostic of triangle normals, adjacency and sampled surface color.

These distributions describe a mesh, not an artistic acceptance score.
"""
import argparse
from collections import defaultdict
import hashlib
import io
import json
from pathlib import Path
import struct

import numpy as np
from PIL import Image

def parse(path):
    blob = path.read_bytes()
    if struct.unpack_from('<4sII', blob) != (b'glTF', 2, len(blob)):
        raise ValueError('Invalid GLB header')
    offset, chunks = 12, {}
    while offset < len(blob):
        length, kind = struct.unpack_from('<II', blob, offset)
        if offset + 8 + length > len(blob) or kind in chunks:
            raise ValueError('Invalid/duplicate chunk')
        chunks[kind] = blob[offset + 8:offset + 8 + length]
        offset += length + 8
    doc = json.loads(chunks[0x4E4F534A])
    binary = chunks[0x004E4942]
    if len(doc.get('nodes', [])) != 1 or len(doc.get('meshes', [])) != 1 or len(doc.get('materials', [])) != 1:
        raise ValueError('Only one node/mesh/material supported')
    if set(doc['nodes'][0]) - {'name', 'mesh'} or doc['nodes'][0].get('mesh') != 0:
        raise ValueError('Transformed, hierarchical or skinned nodes are unsupported')
    if doc.get('skins') or doc.get('animations') or doc['scenes'][doc.get('scene', 0)]['nodes'] != [0]:
        raise ValueError('Requires static, single-instance active scene')
    primitives = doc['meshes'][0]['primitives']
    if len(primitives) != 1 or primitives[0].get('mode', 4) != 4 or primitives[0].get('targets'):
        raise ValueError('Requires one TRIANGLES primitive without morph targets')
    primitive = primitives[0]

    def accessor(index):
        a = doc['accessors'][index]
        if a.get('sparse') or a.get('normalized'):
            raise ValueError('Unsupported sparse or normalized accessor')
        dtype = {5126: '<f4', 5125: '<u4', 5123: '<u2', 5121: 'u1'}[a['componentType']]
        components = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3}[a['type']]
        view = doc['bufferViews'][a['bufferView']]
        if view.get('buffer', 0) != 0:
            raise ValueError('Expected embedded buffer')
        offset = view.get('byteOffset', 0) + a.get('byteOffset', 0)
        item = np.dtype(dtype).itemsize
        stride = view.get('byteStride', item * components)
        return np.ndarray((a['count'], components), dtype=dtype, buffer=binary,
                          offset=offset, strides=(stride, item)).copy()

    attrs = primitive['attributes']
    positions = accessor(attrs['POSITION']).astype(float)
    normals = accessor(attrs['NORMAL']).astype(float)
    uv = accessor(attrs['TEXCOORD_0']).astype(float)
    triangles = accessor(primitive['indices']).reshape(-1, 3).astype(np.int64)
    if triangles.min() < 0 or triangles.max() >= len(positions):
        raise ValueError('Index out of bounds')
    pbr = doc['materials'][0]['pbrMetallicRoughness']
    ti = pbr['baseColorTexture']
    if ti.get('texCoord', 0) != 0 or ti.get('extensions'):
        raise ValueError('Only untransformed UV0 textures supported')
    texture = doc['textures'][ti['index']]
    sampler = doc.get('samplers', [])[texture['sampler']] if 'sampler' in texture else {}
    if any(sampler.get(k, 10497) != 10497 for k in ('wrapS', 'wrapT')):
        raise ValueError('Only repeat wrapping supported')
    metadata = doc['images'][texture['source']]
    view = doc['bufferViews'][metadata['bufferView']]
    image = Image.open(io.BytesIO(binary[view.get('byteOffset', 0):view.get('byteOffset', 0) + view['byteLength']])).convert('RGB')
    pixels = np.asarray(image).astype(float) / 255
    pixels = np.where(pixels <= .04045, pixels / 12.92, ((pixels + .055) / 1.055) ** 2.4)
    pixels *= np.array(pbr.get('baseColorFactor', [1, 1, 1, 1]))[:3]
    return positions, normals, uv, triangles, pixels

def percentiles(x):
    return {f'p{p}': float(np.percentile(x, p)) for p in [0, 10, 25, 50, 75, 90, 95, 100]}

def sample(pixels, uv):
    h, w = pixels.shape[:2]
    xy = uv * np.array([w, -h]) + np.array([-.5, h - .5])
    low = np.floor(xy).astype(int)
    t = xy - low
    x, y = low[:, 0], low[:, 1]
    tx, ty = t[:, 0, None], t[:, 1, None]
    rgb = ((1-tx)*pixels[y % h, x % w] + tx*pixels[y % h, (x+1) % w])*(1-ty)
    rgb += ((1-tx)*pixels[(y+1) % h, x % w] + tx*pixels[(y+1) % h, (x+1) % w])*ty
    return np.where(rgb <= .0031308, rgb * 12.92, 1.055 * np.maximum(rgb, 0)**(1/2.4) - .055) * 255

def analyze(path):
    source_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    positions, normals, uv, triangles, pixels = parse(path)
    corners = positions[triangles]
    cross = np.cross(corners[:, 1]-corners[:, 0], corners[:, 2]-corners[:, 0])
    area2 = np.linalg.norm(cross, axis=1)
    if np.any(area2 <= np.ptp(positions, axis=0).max()**2 * 1e-14):
        raise ValueError('Degenerate geometry requires separate review')
    face_normals = cross / area2[:, None]
    corner_normals = normals[triangles]
    corner_normals /= np.linalg.norm(corner_normals, axis=2)[:, :, None]
    dots = np.einsum('fvc,fc->fv', corner_normals, face_normals)
    unique, welded = np.unique(positions, axis=0, return_inverse=True)
    ids = welded[triangles]
    edges = defaultdict(list)
    for face, tri in enumerate(ids):
        for a, b in [(tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0])]:
            edges[tuple(sorted((int(a), int(b))))].append(face)
    pairs = np.array([faces for faces in edges.values() if len(faces) == 2])
    edge_lengths = np.array([np.linalg.norm(unique[a]-unique[b]) for (a, b), faces in edges.items() if len(faces) == 2])
    dot = np.sum(face_normals[pairs[:, 0]] * face_normals[pairs[:, 1]], axis=1)
    angles = np.degrees(np.arccos(np.clip(dot, -1, 1)))
    weights = np.array([(i/12, j/12, (12-i-j)/12) for i in range(1, 11) for j in range(1, 12-i)])
    coords = np.einsum('fvc,sv->fsc', uv[triangles], weights)
    colors = sample(pixels, coords.reshape(-1, 2)).reshape(len(triangles), len(weights), 3)
    channel_range = np.ptp(colors, axis=1).max(axis=1)
    representatives = np.median(colors, axis=1)
    edge_color_delta = np.linalg.norm(representatives[pairs[:, 0]]-representatives[pairs[:, 1]], axis=1) / np.sqrt(3)
    area = area2 / 2
    result = {
        'source': str(path), 'source_sha256': source_hash,
        'triangles': len(triangles), 'render_vertices': len(positions), 'exact_unique_positions': len(unique),
        'adjacency_method': 'Exact equality of stored positions; no geometry welding or tolerance-based edits',
        'boundary_edges': sum(len(x) == 1 for x in edges.values()),
        'nonmanifold_edges': sum(len(x) > 2 for x in edges.values()),
        'shared_edges': len(pairs),
        'corner_normal_dot_face_normal': percentiles(dots.ravel()),
        'fraction_corners_matching_flat_normal_within_1e_5': float(np.mean(dots >= 1-1e-5)),
        'adjacent_face_angle_degrees': percentiles(angles),
        'angle_fraction_below_degrees': {str(t): float(np.mean(angles < t)) for t in [1, 5, 10, 20, 30]},
        'edge_length_weighted_angle_fraction_below_degrees': {str(t): float(edge_lengths[angles < t].sum()/edge_lengths.sum()) for t in [1, 5, 10, 20, 30]},
        'face_area_relative_to_median': percentiles(area/np.median(area)),
        'texture_size': [pixels.shape[1], pixels.shape[0]], 'samples_per_triangle': len(weights),
        'max_within_face_channel_range_255': percentiles(channel_range),
        'fraction_faces_with_channel_range_above': {str(t): float(np.mean(channel_range > t)) for t in [5, 20, 50, 100]},
        'surface_area_fraction_with_channel_range_above': {str(t): float(area[channel_range > t].sum()/area.sum()) for t in [5, 20, 50, 100]},
        'adjacent_face_median_color_rgb_rms_255': percentiles(edge_color_delta),
        'fraction_edges_angle_below_10_and_color_rms_below_5': float(np.mean((angles < 10) & (edge_color_delta < 5))),
        'source_file_unchanged': source_hash == hashlib.sha256(path.read_bytes()).hexdigest(),
        'scope': 'Global geometric distributions and 55 fixed interior texture samples per face. No semantic body regions, no light-dependent visibility prediction, no full-texel extrema, no identity/art/animation score. High within-face variation may be legitimate coat boundaries or eyes.',
        'quality_acceptance': False
    }
    assert result['source_file_unchanged']
    return result

parser = argparse.ArgumentParser()
parser.add_argument('sources', type=Path, nargs='+')
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
if args.output.exists():
    raise RuntimeError('Preserve prior analysis; choose a new output')
report = {'assets': [analyze(path) for path in args.sources],
          'comparison_limit': 'cat.png is a 2D AI image; its actual mesh topology is unknown. These numbers cannot establish an exact target or prove stylistic similarity.',
          'analysis_only': True}
args.output.write_text(json.dumps(report, indent=2) + '\n')
args.output.with_suffix('.executed.py').write_bytes(Path(__file__).read_bytes())
print(json.dumps(report))
