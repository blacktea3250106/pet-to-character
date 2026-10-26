"""Independent read-only point evaluation after registration; labels never enter the estimator."""
import argparse,json,hashlib
from pathlib import Path
import numpy as np
from scipy.ndimage import map_coordinates

def main():
    p=argparse.ArgumentParser();p.add_argument('--flow',type=Path,required=True);p.add_argument('--labels',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    d=np.load(a.flow);labels=json.loads(a.labels.read_text());rows=[]
    for group in ['landmarks','holdout_landmarks']:
        for name,start,target in labels[group]:
            # Image coordinate annotations refer to pixel positions; both origins are the same.
            x,y=start;delta=np.array([map_coordinates(d['forward'][...,k],[[y],[x]],order=1)[0] for k in range(2)])
            estimated=np.array(start)+delta
            trust=bool(map_coordinates(d['trusted'].astype(float),[[y],[x]],order=0)[0])
            rows.append({'name':name,'group':group,'input':start,'target':target,'estimated':estimated.tolist(),
              'baseline_error_px':float(np.linalg.norm(np.array(start)-target)),
              'flow_error_px':float(np.linalg.norm(estimated-target)),'trusted':trust,
              'fb_error_px':float(map_coordinates(d['fb_error'],[[y],[x]],order=1)[0])})
    def summary(items):
        b=np.array([r['baseline_error_px'] for r in items]);e=np.array([r['flow_error_px'] for r in items])
        return {'n':len(items),'baseline_rms_px':float(np.sqrt((b*b).mean())),'flow_rms_px':float(np.sqrt((e*e).mean())),
          'flow_median_px':float(np.median(e)),'flow_p90_px':float(np.percentile(e,90)),'flow_max_px':float(e.max()),
          'points_over_15px':int((e>15).sum()),'trusted_points':sum(r['trusted'] for r in items),
          'trusted_but_over_15px':[r['name'] for r in items if r['trusted'] and r['flow_error_px']>15]}
    report={'purpose':'All points excluded from estimator. This is retrospective single-case evaluation, not a held-out cat population.',
      'flow_sha256':hashlib.sha256(a.flow.read_bytes()).hexdigest(),'labels_sha256':hashlib.sha256(a.labels.read_bytes()).hexdigest(),
      'all_points':summary(rows),'previously_unused_four_points':summary([r for r in rows if r['group']=='holdout_landmarks']),
      'face_points':summary([r for r in rows if any(s in r['name'] for s in ['eye','nose','mouth','muzzle','cheek','forehead'])]),
      'points':rows,'adopted':False,'review_pending':True}
    a.out.write_text(json.dumps(report,ensure_ascii=False,indent=2));print(json.dumps({k:v for k,v in report.items() if k!='points'},ensure_ascii=False))
if __name__=='__main__':main()
