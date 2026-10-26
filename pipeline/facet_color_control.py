"""Bounded per-triangle color simplification, without semantic coordinates.

High color variation and existing low-roughness faces are left byte-identical.
Thresholds are experimental style controls, not photo-identity guarantees.
"""
import argparse
import hashlib
import json
from pathlib import Path
import cv2
import numpy as np
from PIL import Image
from scipy.ndimage import distance_transform_edt

HERE = Path(__file__).resolve().parent


def linear(c):
    return np.where(c <= .04045, c / 12.92, ((c + .055) / 1.055) ** 2.4)


def srgb(c):
    return np.where(c <= .0031308, c * 12.92, 1.055 * np.maximum(c, 0) ** (1 / 2.4) - .055)


def lab(c):
    return cv2.cvtColor(np.float32(c).reshape(-1, 1, 3), cv2.COLOR_RGB2Lab).reshape(-1, 3)


def uv_owners(uv, height, width):
    if not np.isfinite(uv).all() or uv.min() < 0 or uv.max() > 1:
        raise ValueError('Requires finite UVs in the unit tile')
    coords = np.stack([uv[..., 0] * width, (1 - uv[..., 1]) * height], axis=-1)
    owners = np.full((height, width), -1, np.int32)
    interiors = np.zeros((height, width), np.uint16)
    interior_owner = np.full((height, width), -1, np.int32)
    collision_faces = np.zeros(len(uv), bool)
    for i, (a, b, c) in enumerate(coords):
        lo = np.maximum(np.floor(np.minimum(np.minimum(a, b), c)).astype(int), 0)
        hi = np.minimum(np.ceil(np.maximum(np.maximum(a, b), c)).astype(int), [width - 1, height - 1])
        if np.any(lo > hi):
            continue
        xs, ys = np.meshgrid(np.arange(lo[0], hi[0] + 1) + .5, np.arange(lo[1], hi[1] + 1) + .5)
        den = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
        if abs(den) < 1e-12:
            continue
        l0 = ((b[1] - c[1]) * (xs - c[0]) + (c[0] - b[0]) * (ys - c[1])) / den
        l1 = ((c[1] - a[1]) * (xs - c[0]) + (a[0] - c[0]) * (ys - c[1])) / den
        minimum = np.minimum(np.minimum(l0, l1), 1 - l0 - l1)
        region = np.s_[lo[1]:hi[1] + 1, lo[0]:hi[0] + 1]
        owners[region][minimum >= -1e-7] = i
        inside = minimum > 1e-5
        previous = interior_owner[region]
        collisions = inside & (previous >= 0)
        if collisions.any():
            collision_faces[i] = True
            collision_faces[previous[collisions]] = True
        previous[inside] = i
        interiors[region] += inside.astype(np.uint16)
    return owners, interiors, collision_faces


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('profile', type=Path)
    args = parser.parse_args()
    cfg = json.loads(args.profile.read_text())
    source = (HERE / cfg['source']).resolve()
    out = (HERE / cfg['output']).resolve()
    if source == out or not source.is_relative_to(HERE) or not out.is_relative_to(HERE):
        raise ValueError('Use separate case-local input/output directories')
    out.mkdir(exist_ok=True)
    (out / 'executed-color-source.py').write_bytes(Path(__file__).read_bytes())
    mesh = np.load(source / 'mesh.npz')
    count = len(mesh['tris'])
    if count != cfg['required_triangles']:
        raise ValueError('Unexpected source triangle count')
    rgba = np.array(Image.open(source / 'base-color.png').convert('RGBA'))
    if not (rgba[..., 3] == 255).all():
        raise ValueError('This experiment requires an opaque material')
    rgb = rgba[..., :3].copy()
    roughness = np.array(Image.open(source / 'roughness.png').convert('L')) / 255.
    height, width = rgb.shape[:2]
    if roughness.shape != (height, width):
        raise ValueError('Source color and roughness must share atlas dimensions')
    owners, interiors, collision_faces = uv_owners(mesh['tri_uv'], height, width)
    coverage = owners >= 0
    overlapping = int((interiors > 1).sum())
    uv_report = {'covered_texels': int(coverage.sum()), 'interior_overlap_texels': overlapping,
                 'overlapping_faces_preserved': int(collision_faces.sum()),
                 'source_uv_acceptance': False,
                 'handling': 'Preserve every overlapping triangle, do not repair UVs or silently overwrite colors',
                 'method': 'UV pixel centers; exact shared triangle edges excluded from overlap count',
                 'not_proven': 'Subpixel overlaps and mipmap/padding safety need separate review'}
    (out / 'uv-check.json').write_text(json.dumps(uv_report, indent=2))
    indices = np.flatnonzero(coverage)
    ids = owners.flat[indices]
    order = np.argsort(ids, kind='stable')
    indices, ids = indices[order], ids[order]
    counts = np.bincount(ids, minlength=count)
    ends = np.cumsum(counts)
    starts = ends - counts
    raw_colors = rgb.reshape(-1, 3)[indices]
    colors = np.float32(raw_colors) / 255.
    linear_colors = linear(colors)
    labs = lab(colors)
    low_roughness = roughness.flat[indices] < cfg['roughness_preserve_below']
    means = np.zeros((count, 3), np.uint8)
    radii = np.full(count, np.inf)
    protected = np.zeros(count, bool)
    for i in range(count):
        start, end = starts[i], ends[i]
        if start == end:
            continue
        protected[i] = bool(low_roughness[start:end].any())
        # Quantize the actual output color before measuring the error bound.
        means[i] = np.rint(np.clip(srgb(linear_colors[start:end].mean(axis=0)), 0, 1) * 255).astype(np.uint8)
        center = lab(means[i:i + 1] / 255.)[0]
        radii[i] = np.linalg.norm(labs[start:end] - center, axis=1).max()
    distance, nearest = distance_transform_edt(~coverage, return_indices=True)
    pad = (~coverage) & (distance <= cfg['padding_px'])
    inputs = [source / name for name in ['mesh.npz', 'base-color.png', 'roughness.png']]
    provenance = [{'path': str(p.relative_to(HERE)), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in inputs]
    reports = []
    for variant in cfg['variants']:
        output = out / variant['id']
        if output.exists():
            raise FileExistsError(f'Preserve existing variant: {output}')
        output.mkdir()
        eligible = (radii <= variant['max_delta_e76']) & ~protected & ~collision_faces & (counts >= cfg['min_texels'])
        result = rgb.copy()
        change = eligible[ids]
        result.reshape(-1, 3)[indices[change]] = means[ids[change]]
        unchanged = ~change
        assert np.array_equal(result.reshape(-1, 3)[indices[unchanged]], raw_colors[unchanged])
        result[pad] = result[nearest[0][pad], nearest[1][pad]]
        assert np.array_equal(result[interiors > 1], rgb[interiors > 1])
        Image.fromarray(result).save(output / 'base-color.png')
        altered = np.zeros((height, width), np.uint8)
        altered.flat[indices[change]] = 255
        Image.fromarray(altered).save(output / 'eligible-texels.png')
        delta = np.linalg.norm(lab(result.reshape(-1, 3)[indices] / 255.) - labs, axis=1)
        report = {'variant': variant['id'], 'inputs': provenance, 'config': cfg, 'uv': uv_report,
                  'total_faces': count, 'eligible_faces': int(eligible.sum()),
                  'eligible_fraction_of_covered_texels': float(change.mean()),
                  'protected_low_roughness_faces': int(protected.sum()),
                  'high_variation_or_unsampled_faces': int((radii > variant['max_delta_e76']).sum()),
                  'actual_changed_covered_texels': int(np.any(result.reshape(-1, 3)[indices] != raw_colors, axis=1).sum()),
                  'max_covered_texel_delta_e76': float(delta.max()),
                  'preserved_faces_byte_identical': True,
                  'protected_faces_automatically_located': False,
                  'protection_source': 'Existing roughness map from manually assisted upstream eye/material work; no new regions',
                  'semantic_identity_preservation_proven': False, 'art_pass': False,
                  'new_cat_automation_proven': False, 'geometry_or_uv_modified': False}
        assert delta.max() <= variant['max_delta_e76'] + 1e-4
        (output / 'processing-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
        reports.append({k: report[k] for k in ['variant', 'eligible_faces', 'eligible_fraction_of_covered_texels', 'max_covered_texel_delta_e76', 'protected_low_roughness_faces']})
    np.savez_compressed(out / 'face-diagnostics.npz', face_id=owners, covered=coverage, max_delta_e76=radii, protected=protected, collision_faces=collision_faces)
    print(json.dumps(reports), flush=True)


if __name__ == '__main__':
    main()
