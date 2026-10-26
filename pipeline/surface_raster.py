"""Raster helpers adapted from read-only catworld/proj_bake.py; no application imports."""
import numpy as np

def raster_tris(P, size, attrs):
    """Rasterise triangles P (T,3,2) in pixel coords. attrs: (T,3,C) per-corner values.
    Returns (mask, out (H,W,C), tri_id) with barycentric interpolation; last write wins."""
    H, W = size
    C = attrs.shape[2]
    out = np.zeros((H, W, C), np.float32)
    tid = np.full((H, W), -1, np.int32)
    for t in range(len(P)):
        a, b, c = P[t]
        x0, x1 = (int(max(np.floor(min(a[0], b[0], c[0])), 0)), int(min(np.ceil(max(a[0], b[0], c[0])), W - 1)))
        y0, y1 = (int(max(np.floor(min(a[1], b[1], c[1])), 0)), int(min(np.ceil(max(a[1], b[1], c[1])), H - 1)))
        if x1 < x0 or y1 < y0:
            continue
        xs, ys = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
        den = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
        if abs(den) < 1e-12:
            continue
        l0 = ((b[1] - c[1]) * (xs - c[0]) + (c[0] - b[0]) * (ys - c[1])) / den
        l1 = ((c[1] - a[1]) * (xs - c[0]) + (a[0] - c[0]) * (ys - c[1])) / den
        l2 = 1 - l0 - l1
        inside = (l0 >= -0.0001) & (l1 >= -0.0001) & (l2 >= -0.0001)
        if not inside.any():
            continue
        val = l0[..., None] * attrs[t, 0] + l1[..., None] * attrs[t, 1] + l2[..., None] * attrs[t, 2]
        sub = out[y0:y1 + 1, x0:x1 + 1]
        sub[inside] = val[inside]
        tid[y0:y1 + 1, x0:x1 + 1][inside] = t
    return (tid >= 0, out, tid)

def zbuffer(uv, depth, tris, size):
    H, W = size
    zb = np.full((H, W), -np.inf, np.float32)
    for t in tris:
        a, b, c = uv[t]
        x0, x1 = (int(max(np.floor(min(a[0], b[0], c[0])), 0)), int(min(np.ceil(max(a[0], b[0], c[0])), W - 1)))
        y0, y1 = (int(max(np.floor(min(a[1], b[1], c[1])), 0)), int(min(np.ceil(max(a[1], b[1], c[1])), H - 1)))
        if x1 < x0 or y1 < y0:
            continue
        xs, ys = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
        den = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
        if abs(den) < 1e-12:
            continue
        l0 = ((b[1] - c[1]) * (xs - c[0]) + (c[0] - b[0]) * (ys - c[1])) / den
        l1 = ((c[1] - a[1]) * (xs - c[0]) + (a[0] - c[0]) * (ys - c[1])) / den
        l2 = 1 - l0 - l1
        inside = (l0 >= -0.0001) & (l1 >= -0.0001) & (l2 >= -0.0001)
        z = l0 * depth[t[0]] + l1 * depth[t[1]] + l2 * depth[t[2]]
        sub = zb[y0:y1 + 1, x0:x1 + 1]
        np.maximum(sub, np.where(inside, z, -np.inf), out=sub)
    return zb
