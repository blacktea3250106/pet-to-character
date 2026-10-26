"""Independent fixture jobs; failed fits are recorded and never silently filled."""
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from pathlib import Path
import subprocess
import sys

P=Path(__file__).resolve().parent
BLENDER='/Applications/Blender.app/Contents/MacOS/Blender'
manifest=json.loads((P/'stress-inputs/manifest.json').read_text())

def one(case):
    name=case['case'];result={'case':name,'steps':[],'status':'running'}
    jobs=[('fit',[sys.executable,str(P/'fit_parts.py'),'--case',name,'--target-npz',str(P/'stress-inputs'/case['path']),'--output','fit-v002','--arap']),
          ('bind',[BLENDER,'--background','--threads','2','--python-exit-code','1','--python',str(P/'build_candidate.py'),'--','--case',name,'--diagnostic-only']),
          ('sampled_animation',[BLENDER,'--background','--threads','2','--python-exit-code','1','--python',str(P.parent/'27-animation-compatibility/bake_and_measure.py'),'--',str(P/'fit-v002'/name/'candidate'),'--checkpoints-only'])]
    for step,argv in jobs:
        log=P/f'stress-{name}-{step}.log'
        with log.open('w') as f:job=subprocess.run(argv,stdout=f,stderr=subprocess.STDOUT)
        result['steps'].append({'step':step,'exit_code':job.returncode,'log':log.name})
        if job.returncode:
            result['status']='rejected_at_'+step;break
    else:result['status']='diagnostics_completed_not_quality_pass'
    (P/f'stress-{name}-status.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result),flush=True);return result

with ThreadPoolExecutor(max_workers=2) as pool:
    results=[f.result() for f in as_completed([pool.submit(one,case) for case in manifest['cases']])]
(P/'stress-run.json').write_text(json.dumps({'cases':results,'coverage':'15 poses per successful fixture, not full clips','new_cat_automation_proven':False},indent=2)+'\n')
