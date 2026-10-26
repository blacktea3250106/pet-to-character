"""Geometry-only foot groups for standardized standing meshes; reject ambiguity."""
from pathlib import Path
import json
import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components

P = Path(__file__).resolve().parent


def foot_groups(points, triangles):
    # Weld only an analysis copy; input UV vertices are never edited.
    span = np.ptp(points, axis=0).max()
    _, first, inverse = np.unique(np.rint(points / (span * 1e-7)).astype(np.int64), axis=0, return_index=True, return_inverse=True)
    v, f = points[first], inverse[triangles]
    edges = np.vstack([f[:, [0, 1]], f[:, [1, 2]], f[:, [2, 0]]])
    edges = np.vstack([edges, edges[:, ::-1]])
    graph = coo_matrix((np.ones(len(edges)), (edges[:, 0], edges[:, 1])), shape=(len(v), len(v))).tocsr()
    z0, height = v[:, 2].min(), np.ptp(v[:, 2])
    scans, candidates = [], []
    for fraction in np.arange(.04, .661, .02):
        included = np.flatnonzero(v[:, 2] <= z0 + height * fraction)
        n, labels = connected_components(graph[included][:, included], directed=False)
        groups = [included[labels == i] for i in range(n) if (labels == i).sum() >= 5]
        scans.append({'fraction': float(fraction), 'components': len(groups), 'sizes': [len(g) for g in groups]})
        if len(groups) == 4:
            candidates.append((fraction, groups))
        elif candidates and len(groups) < 4:
            break
    if len(candidates) < 3:
        raise ValueError('Four separated low limbs not stable across three height cuts')
    fraction, groups = candidates[0]
    centers = np.array([np.median(v[g], axis=0) for g in groups])
    order = np.argsort(centers[:, 0])
    result = {}
    for label, pair in [('rear', order[:2]), ('front', order[2:])]:
        pair = pair[np.argsort(centers[pair, 1])]
        for side, i in zip(['R', 'L'], pair):
            g = groups[i]
            result[f'{label}_{side}'] = {'point': [float(centers[i, 0]), float(centers[i, 1]), float(z0)],
                                        'analysis_vertices': g.tolist()}
    front = np.mean([result[k]['point'][0] for k in ['front_L', 'front_R']])
    rear = np.mean([result[k]['point'][0] for k in ['rear_L', 'rear_R']])
    if front - rear < .2 * np.ptp(v[:, 0]):
        raise ValueError('Ambiguous front/rear feet')
    return {'feet': result, 'ground': float(z0), 'last_four_limb_height': float(z0 + candidates[-1][0] * height),
            'first_stable_fraction': float(fraction), 'scan': scans, 'scope': 'Four low connected limb groups under known forward/up axes; not general animal pose recognition'}


report = {}
for kind in ['source', 'target']:
    data = np.load(P / f'inventory/{kind}-mesh.npz')
    pts = data['vertices'].copy()
    if kind == 'source':
        pts = np.column_stack([-pts[:, 1], pts[:, 0], pts[:, 2]])
    report[kind] = foot_groups(pts, data['triangles'])
src, tgt = report['source'], report['target']
labels = ['front_L', 'front_R', 'rear_L', 'rear_R']
a = np.array([src['feet'][k]['point'] for k in labels])
b = np.array([tgt['feet'][k]['point'] for k in labels])
scale = np.ones(3)
offset = np.zeros(3)
for axis in [0, 1]:
    scale[axis] = np.dot(a[:, axis] - a[:, axis].mean(), b[:, axis] - b[:, axis].mean()) / np.var(a[:, axis]) / len(a)
    offset[axis] = b[:, axis].mean() - scale[axis] * a[:, axis].mean()
scale[2] = (tgt['last_four_limb_height'] - tgt['ground']) / (src['last_four_limb_height'] - src['ground'])
offset[2] = tgt['ground'] - scale[2] * src['ground']
assert (scale > 0).all()
report['affine_initialization'] = {'scale': scale.tolist(), 'offset': offset.tolist(), 'foot_residuals': np.linalg.norm(a * scale + offset - b, axis=1).tolist(),
                                    'warning': 'Only an initial alignment. Does not prove head/tail correspondence or joint placement.'}
(P / 'foot-detection.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps({'source_feet': {k:v['point'] for k,v in src['feet'].items()}, 'target_feet': {k:v['point'] for k,v in tgt['feet'].items()}, 'initialization':report['affine_initialization']}))
