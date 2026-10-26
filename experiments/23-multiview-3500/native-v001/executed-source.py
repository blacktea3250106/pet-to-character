"""Submit one approved, hash-bound multiview generation; no local remeshing."""
import argparse, fcntl, hashlib, json, sys, time
from datetime import datetime
from pathlib import Path
import requests
from PIL import Image
from tripo_run import api, write
from glb_preflight import inspect_glb

HERE = Path(__file__).resolve().parent


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(config_path, dry_run):
    cfg = json.loads(config_path.read_text())
    review_path = HERE / cfg['reference_review']
    review = json.loads(review_path.read_text())
    if review.get('approved_for_poc_submission') is not True:
        raise RuntimeError('Reference gate has not approved generation')
    params = json.loads((HERE / cfg['request_profile']).read_text())['tripo']['request_parameters']
    if cfg['endpoint'] != '/generation/multiview-to-model' or params['face_limit'] != 3500 or params['quad'] or not params['smart_low_poly']:
        raise RuntimeError('Request differs from the authorized native triangle-budget experiment')
    selected = review['selected']
    if 'front' not in selected or not 2 <= len(selected) <= 4 or set(selected) - {'front','left','back','right'}:
        raise RuntimeError('Invalid view selection')
    inputs = []
    for view in ('front','left','back','right'):
        if view not in selected: continue
        path = review_path.parent / selected[view]
        if digest(path) != review['input_hashes'][view]:
            raise RuntimeError('Image changed after visual approval')
        with Image.open(path) as im:
            im.load()
            if im.format not in ('PNG','JPEG','WEBP') or min(im.size) < 256:
                raise RuntimeError('Unsupported input image')
            inputs.append({'view':view,'file':str(path.relative_to(HERE)), 'sha256':digest(path),
                           'dimensions':list(im.size),'mime':Image.MIME[im.format]})
    public = {'endpoint':cfg['endpoint'],'inputs':inputs,'parameters':params,
              'reference_review_sha256':digest(review_path),'expected_credits':cfg['expected_credits']}
    fingerprint = hashlib.sha256(json.dumps(public,sort_keys=True).encode()).hexdigest()
    if dry_run:
        print(json.dumps({**public,'network_requests':0},ensure_ascii=False,indent=2));return
    out = HERE / cfg['output'];out.mkdir(parents=True,exist_ok=True)
    with (out/'.run.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        statefile = out/'state.json';state=json.loads(statefile.read_text()) if statefile.exists() else {}
        if state and state['request_fingerprint'] != fingerprint:
            raise RuntimeError('Existing state is bound to a different request')
        if state.get('status') == 'downloaded':
            for item in state['downloads']:
                if digest(out/item['file']) != item['sha256']:raise RuntimeError('Downloaded artifact changed')
            print('Completed artifacts verified; no network or paid submission');return
        if not state.get('task_id'):
            if state.get('submission_started'):raise RuntimeError('Unknown prior POST; no resubmission')
            write(out/'request-public.json',public)
            for source, dest in [('tripo_generate_views.py','executed-source.py'),('tripo_run.py','executed-api-helper.py'),('glb_preflight.py','executed-preflight.py')]:
                (out/dest).write_bytes((HERE/source).read_bytes())
            tokens=[]
            for item in inputs:
                path=HERE/item['file']
                with path.open('rb') as f:
                    token=api('POST','/files',files={'file':(path.name,f,item['mime'])})['file_token']
                tokens.append({item['view']:token});print('Uploaded',item['view'],flush=True)
            state={'submission_started':True,'started_at':time.time(),'request_fingerprint':fingerprint,'status':'submitting'}
            write(statefile,state)
            try:
                task=api('POST',cfg['endpoint'],json={'inputs':tokens,**params})
                state['task_id']=task['task_id']
            except Exception as exc:
                state['submission_error_type']=type(exc).__name__;write(statefile,state);raise
            write(statefile,state);print('task_id',state['task_id'],flush=True)
        previous=None
        for _ in range(150):
            task=api('GET','/tasks/'+state['task_id']);status=task.get('status');progress=task.get('progress')
            safe={k:task.get(k) for k in ('task_id','type','status','progress','credits_consumed','created_at','completed_at','error_code')}
            safe['received_parameters']={k:v for k,v in task.get('input',{}).items() if k in params or k=='model_version'}
            safe['output_keys']=list(task.get('output',{}));write(out/'task-status.json',safe)
            if (status,progress)!=previous:print(status,progress,flush=True);previous=(status,progress)
            if status=='success':break
            if status in ('failed','cancelled','canceled','banned','expired'):
                state.update(status=status,credits_consumed=task.get('credits_consumed'));write(statefile,state)
                raise RuntimeError('Generation terminated; no automatic paid retry')
            time.sleep(8)
        else:raise RuntimeError('Soft polling deadline; resume this task')
        state.update(status='success_pending_download',credits_consumed=task.get('credits_consumed',task.get('consumed_credit')));write(statefile,state)
        downloads=[]
        for name,url in task.get('output',{}).items():
            if not isinstance(url,str) or not url.startswith('https://') or not any(k in name for k in ('model','rendered','texture')):continue
            response=requests.get(url,timeout=180)
            if response.status_code!=200:raise RuntimeError('Asset download HTTP failure')
            blob=response.content
            ext='.glb' if blob[:4]==b'glTF' else '.png' if blob[:8]==b'\x89PNG\r\n\x1a\n' else '.jpg' if blob[:3]==b'\xff\xd8\xff' else '.zip' if blob[:2]==b'PK' else '.bin'
            path=out/(name+ext);path.write_bytes(blob)
            item={'kind':name,'file':path.name,'bytes':len(blob),'sha256':digest(path)}
            if ext=='.glb':
                report=inspect_glb(path,params['face_limit']);write(out/(name+'-preflight.json'),report)
                item.update(triangles=report['active_scene_triangles'],budget_pass=report['budget_pass'])
            downloads.append(item);print('Downloaded',path.name,item.get('triangles',''),flush=True)
        if not any(x['file'].endswith('.glb') for x in downloads):raise RuntimeError('No actual GLB output; inspect output_keys')
        state.update(status='downloaded',downloads=downloads,elapsed_seconds=round(time.time()-state['started_at'],2),asset_accepted=False)
        if task.get('created_at') and task.get('completed_at'):
            state['server_task_seconds']=round((datetime.fromisoformat(task['completed_at'])-datetime.fromisoformat(task['created_at'])).total_seconds(),3)
        write(statefile,state)
        print(json.dumps({'status':state['status'],'credits_consumed':state['credits_consumed'],'elapsed_seconds':state['elapsed_seconds'],'downloads':downloads}),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('config',type=Path);parser.add_argument('--dry-run',action='store_true');args=parser.parse_args()
    try:run(args.config,args.dry_run)
    except Exception as exc:
        print('Generation stopped:',type(exc).__name__,'Inspect sanitized state; do not resubmit blindly.',flush=True);sys.exit(1)
