"""Bounded-error color facets on existing UV triangles, without mesh edits.

Each virtual child is a region of a texture, not added geometry. High-variation
cells keep their original pixels. This is not semantic eye/identity detection.
"""
import argparse
import copy
import hashlib
import io
import json
from pathlib import Path
import struct

import cv2
import numpy as np
from PIL import Image
from scipy.ndimage import distance_transform_edt

from glb_preflight import inspect_glb


def read_glb(path):
    blob = path.read_bytes()
    if struct.unpack_from('<4sII', blob) != (b'glTF', 2, len(blob)):
        raise ValueError('Invalid GLB')
    cursor, chunks = 12, []
    while cursor < len(blob):
        size, kind = struct.unpack_from('<II', blob, cursor)
        if size % 4 or cursor + 8 + size > len(blob):
            raise ValueError('Invalid chunk boundary')
        chunks.append((kind, blob[cursor + 8:cursor + 8 + size]))
        cursor += 8 + size
    if [k for k, _ in chunks] != [0x4e4f534a, 0x004e4942]:
        raise ValueError('Requires JSON and embedded BIN')
    return json.loads(chunks[0][1]), chunks[1][1]


def write_glb(path, doc, binary):
    js = json.dumps(doc, separators=(',', ':')).encode()
    js += b' ' * (-len(js) % 4)
    binary += b'\0' * (-len(binary) % 4)
    body = struct.pack('<II', len(js), 0x4e4f534a) + js
    body += struct.pack('<II', len(binary), 0x004e4942) + binary
    path.write_bytes(struct.pack('<4sII', b'glTF', 2, len(body) + 12) + body)


def accessor(doc, binary, index):
    a = doc['accessors'][index]
    if a.get('normalized') or a.get('sparse'):
        raise ValueError('Unsupported accessor')
    view = doc['bufferViews'][a['bufferView']]
    if view.get('buffer', 0) != 0:
        raise ValueError('Non-embedded buffer')
    dtype = np.dtype({5126: '<f4', 5125: '<u4', 5123: '<u2'}[a['componentType']])
    channels = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3}[a['type']]
    return np.ndarray((a['count'], channels), dtype=dtype, buffer=binary,
                      offset=view.get('byteOffset', 0) + a.get('byteOffset', 0),
                      strides=(view.get('byteStride', dtype.itemsize * channels), dtype.itemsize)).copy()


def lab(rgb):
    return cv2.cvtColor(np.float32(rgb).reshape(-1, 1, 3) / 255, cv2.COLOR_RGB2Lab).reshape(-1, 3)


def rasterize(uv, height, width):
    """Direct GLB UV origin is upper-left, same as decoded image rows."""
    if not np.isfinite(uv).all() or uv.min() < 0 or uv.max() > 1:
        raise ValueError('Requires UVs inside one unit tile')
    coords = uv * np.array([width, height])
    owners = np.full((height, width), -1, np.int32)
    interior_owner = np.full((height, width), -1, np.int32)
    collisions = np.zeros(len(uv), bool)
    bary = np.zeros((height, width, 3), np.float32)
    overlap = np.zeros((height, width), bool)
    for face, (a, b, c) in enumerate(coords):
        lo = np.maximum(np.floor(np.min([a, b, c], axis=0)).astype(int), 0)
        hi = np.minimum(np.ceil(np.max([a, b, c], axis=0)).astype(int), [width - 1, height - 1])
        if np.any(hi < lo):
            continue
        x, y = np.meshgrid(np.arange(lo[0], hi[0] + 1) + .5, np.arange(lo[1], hi[1] + 1) + .5)
        den = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
        if abs(den) < 1e-12:
            continue
        w0 = ((b[1] - c[1]) * (x - c[0]) + (c[0] - b[0]) * (y - c[1])) / den
        w1 = ((c[1] - a[1]) * (x - c[0]) + (a[0] - c[0]) * (y - c[1])) / den
        ws = np.stack([w0, w1, 1 - w0 - w1], -1)
        minimum = ws.min(-1)
        region = np.s_[lo[1]:hi[1] + 1, lo[0]:hi[0] + 1]
        inside = minimum > 1e-5
        previous = interior_owner[region]
        conflict = inside & (previous >= 0)
        if conflict.any():
            collisions[face] = True
            collisions[previous[conflict]] = True
            overlap[region][conflict] = True
        previous[inside] = face
        covered = minimum >= -1e-7
        owners[region][covered] = face
        bary[region][covered] = ws[covered]
    return owners, bary, collisions, overlap


def embedded_candidate(path, doc, binary, png, image_index):
    after = copy.deepcopy(doc)
    start = len(binary)
    new_binary = binary + png
    new_binary += b'\0' * (-len(new_binary) % 4)
    new_view = len(after['bufferViews'])
    after['bufferViews'].append({'buffer': 0, 'byteOffset': start, 'byteLength': len(png)})
    after['images'][image_index]['bufferView'] = new_view
    after['images'][image_index]['mimeType'] = 'image/png'
    after['buffers'][0]['byteLength'] = len(new_binary)
    write_glb(path, after, new_binary)
    reread, rb = read_glb(path)
    assert rb[:len(binary)] == binary
    restored = copy.deepcopy(reread)
    restored['images'] = doc['images']
    restored['bufferViews'] = restored['bufferViews'][:-1]
    restored['buffers'] = doc['buffers']
    assert restored == doc, 'Unexpected GLB metadata change'
    im = reread['images'][image_index]
    view = reread['bufferViews'][im['bufferView']]
    assert rb[view['byteOffset']:view['byteOffset'] + view['byteLength']] == png
    return {'original_binary_prefix_identical': True,
            'only_image_binding_and_appended_image_buffer_changed': True,
            'geometry_uv_normals_materials_identical': True,
            'texture_roundtrip_bytes_identical': True}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('profile', type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    cfg = json.loads(args.profile.read_text())
    source, out = root / cfg['source'], root / cfg['output']
    if out.exists():
        raise FileExistsError('Use a fresh output directory')
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    if source_hash != cfg['source_sha256']:
        raise ValueError('Source changed since experiment gate')
    doc, binary = read_glb(source)
    if len(doc.get('meshes', [])) != 1 or len(doc.get('materials', [])) != 1 or len(doc.get('images', [])) != 1:
        raise ValueError('Only one mesh, material and image supported for this experiment')
    if len(doc.get('nodes', [])) != 1 or set(doc['nodes'][0]) - {'mesh', 'name'} or doc.get('skins') or doc.get('animations'):
        raise ValueError('Only a single untransformed static model supported')
    prims = doc['meshes'][0]['primitives']
    if len(prims) != 1 or prims[0].get('mode', 4) != 4 or prims[0].get('targets'):
        raise ValueError('Requires one static triangle primitive')
    prim = prims[0]
    indices = accessor(doc, binary, prim['indices']).reshape(-1, 3)
    uv = accessor(doc, binary, prim['attributes']['TEXCOORD_0'])[indices].astype(float)
    if len(indices) != cfg['required_triangles']:
        raise ValueError('Unexpected face count')
    material = doc['materials'][0]
    pbr = material['pbrMetallicRoughness']
    binding = pbr['baseColorTexture']
    if material.get('alphaMode', 'OPAQUE') != 'OPAQUE' or binding.get('extensions') or binding.get('texCoord', 0) != 0:
        raise ValueError('Opaque material and untransformed UV0 required')
    if pbr.get('baseColorFactor', [1, 1, 1, 1]) != [1, 1, 1, 1]:
        raise ValueError('Non-unit base color factor not supported')
    # Reject other uses of this sole image; replacing it must only change base color.
    other = copy.deepcopy(material)
    del other['pbrMetallicRoughness']['baseColorTexture']
    if 'Texture' in json.dumps(other) or len(doc['textures']) != 1:
        raise ValueError('Shared texture or additional material maps require separate handling')
    image_index = doc['textures'][binding['index']]['source']
    meta = doc['images'][image_index]
    view = doc['bufferViews'][meta['bufferView']]
    raw = binary[view.get('byteOffset', 0):view.get('byteOffset', 0) + view['byteLength']]
    rgba = np.asarray(Image.open(io.BytesIO(raw)).convert('RGBA'))
    if not (rgba[..., 3] == 255).all():
        raise ValueError('Opaque image required')
    rgb = rgba[..., :3].copy()
    height, width = rgb.shape[:2]
    owners, bary, collisions, overlap = rasterize(uv, height, width)
    cov = owners >= 0
    flat_ids = np.flatnonzero(cov)
    order = np.argsort(owners.flat[flat_ids], kind='stable')
    flat_ids = flat_ids[order]
    face_ids = owners.flat[flat_ids]
    counts = np.bincount(face_ids, minlength=len(indices))
    end = np.cumsum(counts)
    start = end - counts
    source_pixels = rgb.reshape(-1, 3)
    colors_lab = lab(source_pixels)
    weights = bary.reshape(-1, 3)
    distance, nearest = distance_transform_edt(~cov, return_indices=True)
    pad = (~cov) & (distance <= cfg['padding_pixels'])
    out.mkdir(parents=True)
    (out / 'executed-source.py').write_bytes(Path(__file__).read_bytes())
    (out / 'executed-profile.json').write_bytes(args.profile.read_bytes())
    (out / 'executed-preflight.py').write_bytes((root / 'glb_preflight.py').read_bytes())
    Image.fromarray(rgb).save(out / 'source-base-color.png')
    np.savez_compressed(out / 'surface-map.npz', owners=owners, collision_faces=collisions)
    reports = []
    for variant in cfg['variants']:
        target = out / variant['id']
        target.mkdir()
        result = source_pixels.copy()
        flat_level = np.full(len(result), -1, np.int8)
        leaves = {'flat': [0] * (cfg['max_subdivision_depth'] + 1), 'preserved': 0}

        def process(ids, local_weights, depth):
            if len(ids) < cfg['min_cell_texels']:
                leaves['preserved'] += 1
                return
            labs = colors_lab[ids]
            center = np.median(labs, axis=0)
            chosen = np.argmin(np.sum((labs - center) ** 2, axis=1))
            representative = source_pixels[ids[chosen]]
            error = np.linalg.norm(labs - labs[chosen], axis=1)
            if float(error.max()) <= variant['max_delta_e76']:
                result[ids] = representative
                flat_level[ids] = depth
                leaves['flat'][depth] += 1
                return
            if depth == cfg['max_subdivision_depth']:
                leaves['preserved'] += 1
                return
            maximum = local_weights.argmax(1)
            child = np.where(local_weights.max(1) >= .5, maximum, 3)
            for k in range(4):
                select = child == k
                if not select.any():
                    continue
                if k == 3:
                    local = 1 - 2 * local_weights[select]
                else:
                    local = 2 * local_weights[select]
                    local[:, k] -= 1
                process(ids[select], local, depth + 1)

        for face in range(len(indices)):
            if collisions[face]:
                continue
            ids = flat_ids[start[face]:end[face]]
            if len(ids):
                process(ids, weights[ids], 0)
        untouched = flat_level < 0
        assert np.array_equal(result[untouched], source_pixels[untouched])
        delta = np.linalg.norm(lab(result[flat_ids]) - colors_lab[flat_ids], axis=1)
        assert float(delta.max()) <= variant['max_delta_e76'] + 1e-4
        image = result.reshape(height, width, 3)
        image[pad] = image[nearest[0][pad], nearest[1][pad]]
        assert np.array_equal(image[overlap], rgb[overlap])
        texture = target / 'base-color.png'
        Image.fromarray(image).save(texture)
        level_image = np.zeros((height, width, 3), np.uint8)
        legend = [(57, 181, 74), (242, 181, 51), (62, 125, 225)]
        for depth, color in enumerate(legend):
            level_image.reshape(-1, 3)[flat_level == depth] = color
        level_image[cov & (flat_level.reshape(height, width) < 0)] = (200, 70, 150)
        Image.fromarray(level_image).save(target / 'processing-regions.png')
        checks = embedded_candidate(target / 'cat.glb', doc, binary, texture.read_bytes(), image_index)
        preflight = inspect_glb(target / 'cat.glb', cfg['required_triangles'])
        (target / 'preflight.json').write_text(json.dumps(preflight, indent=2) + '\n')
        report = {
            'variant': variant, 'source_sha256': source_hash,
            'output_sha256': hashlib.sha256((target / 'cat.glb').read_bytes()).hexdigest(),
            'triangles': len(indices), 'texture_size': [width, height],
            'uv_origin': 'glTF upper-left; decoded image upper-left',
            'covered_texels': int(cov.sum()), 'overlap_texels': int(overlap.sum()),
            'overlap_faces_preserved': int(collisions.sum()),
            'flat_cells_by_depth': leaves['flat'], 'preserved_cells': leaves['preserved'],
            'flattened_coverage_fraction': float((flat_level[flat_ids] >= 0).mean()),
            'changed_coverage_fraction': float((delta > 1e-6).mean()),
            'max_covered_delta_e76': float(delta.max()), 'mean_covered_delta_e76': float(delta.mean()),
            'preserved_pixels_identical': True, **checks,
            'processing_regions_legend': {'green': 'one color on original face', 'orange': 'one color on quarter-face', 'blue': 'one color on sixteenth-face', 'magenta': 'original source preserved', 'black': 'outside UV coverage'},
            'pixel_bound_limit': 'Applies to decoded covered texel centers, not filtered mipmap samples, source-photo accuracy or semantic identity.',
            'eye_detection': 'None; bounded color change and high-variation preservation only',
            'art_pass': False, 'identity_pass': False, 'animation_pass': False,
            'new_cat_automation_proven': False,
            'versions': {'numpy': np.__version__, 'opencv': cv2.__version__}
        }
        (target / 'processing-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
        reports.append(report)
        print(json.dumps({k: report[k] for k in ['variant', 'flattened_coverage_fraction', 'max_covered_delta_e76', 'flat_cells_by_depth']}), flush=True)
    assert hashlib.sha256(source.read_bytes()).hexdigest() == source_hash
    (out / 'summary.json').write_text(json.dumps({'source_unchanged': True, 'variants': reports}, ensure_ascii=False, indent=2) + '\n')


if __name__ == '__main__':
    main()
