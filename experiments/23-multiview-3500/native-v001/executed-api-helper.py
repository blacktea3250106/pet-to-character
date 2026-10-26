"""One resumable V3 generation. Never prints secrets or re-submits an unknown POST."""
import argparse,hashlib,json,os,sys,time
from pathlib import Path
import requests

HERE=Path(__file__).resolve().parent
SINGLE=False
OUT=HERE/'05-tripo'
OPTIONS=None
BASE='https://openapi.tripo3d.ai/v3'

def write(path,data):
    tmp=path.with_suffix(path.suffix+'.tmp')
    tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2));tmp.replace(path)

def key():
    val=os.environ.get('TRIPO_API_KEY')
    if not val:
        for line in Path(os.environ.get('TRIPO_ENV_FILE', '.env')).read_text().splitlines():
            if line.startswith('TRIPO_API_KEY='):
                val=line.split('=',1)[1].strip().strip('\"\'');break
    if not val: raise RuntimeError('TRIPO_API_KEY is not configured')
    return val

def api(method,path,**kwargs):
    r=requests.request(method,BASE+path,headers={'Authorization':'Bearer '+key()},timeout=120,**kwargs)
    try: body=r.json()
    except ValueError: raise RuntimeError(f'HTTP {r.status_code}; non-JSON response')
    if r.status_code!=200 or body.get('code',0)!=0:
        raise RuntimeError(f'HTTP {r.status_code}; code={body.get("code")}; message={str(body.get("message",body.get("msg","")))[:180]}')
    return body.get('data',body)

def run():
    OUT.mkdir(parents=True,exist_ok=True)
    statefile=OUT/'state.json'
    state=json.loads(statefile.read_text()) if statefile.exists() else {}
    if state.get('status')=='downloaded':
        print('Already downloaded; no new request.');return
    if not state.get('task_id'):
        if state.get('submission_started'):
            raise RuntimeError('Previous submission unresolved; do not submit again.')
        gate=json.loads((HERE/('04b-single-reference' if SINGLE else '04-views')/'review.json').read_text())
        if not gate.get('approved_for_poc_submission'): raise RuntimeError('Reference quality gate not approved')
        profile=json.loads((HERE.parent/'workflow-validation-v001/front-end-profile.json').read_text())
        params=profile['tripo']['request_parameters'].copy()
        if OPTIONS and OPTIONS.request_baseline:
            baseline=json.loads(Path(OPTIONS.request_baseline).read_text())
            params={k:v for k,v in baseline.items() if k not in ['inputs','enable_image_autofix']}
        if OPTIONS and OPTIONS.face_limit is not None:
            params['face_limit']=OPTIONS.face_limit
        if OPTIONS and OPTIONS.dry_run:
            print(json.dumps({'output':str(OUT),'single':SINGLE,'parameters':params,'network_requests':0},indent=2));return
        (OUT/'executed-source.py').write_bytes(Path(__file__).read_bytes())
        uploads=[];inputs=[]
        for view in (['standing'] if SINGLE else ['front','left','back','right']):
            p=HERE/('04b-single-reference' if SINGLE else '04-views')/f'{view}.png'
            if OPTIONS and OPTIONS.request_baseline:
                expected=next(x['sha256'] for x in baseline['inputs'] if x['view']==view)
                if hashlib.sha256(p.read_bytes()).hexdigest()!=expected:
                    raise RuntimeError('Baseline input image hash changed; abort controlled comparison')
            with p.open('rb') as f: d=api('POST','/files',files={'file':(p.name,f,'image/png')})
            token=d['file_token'];inputs.append({view:token})
            uploads.append({'view':view,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
            print('uploaded',view,flush=True)
        request=({'input':inputs[0]['standing'],'enable_image_autofix':False,**params} if SINGLE else {'inputs':inputs,**params})
        write(OUT/'request-public.json',{'inputs':uploads,**({'enable_image_autofix':False} if SINGLE else {}),**params})
        state={'submission_started':True,'started_at':time.time(),'request_sha256':hashlib.sha256(json.dumps(request,sort_keys=True).encode()).hexdigest()}
        write(statefile,state)
        try: task=api('POST','/generation/image-to-model' if SINGLE else '/generation/multiview-to-model',json=request)
        except Exception as e:
            state['submission_error']=str(e);write(statefile,state);raise
        state['task_id']=task['task_id'];write(statefile,state)
        print('task_id',state['task_id'],flush=True)
    last=None
    for _ in range(180):
        d=api('GET','/tasks/'+state['task_id'])
        status=d.get('status');progress=d.get('progress')
        clean={k:v for k,v in d.items() if k!='output'}
        clean['output_keys']=list(d.get('output',{}))
        write(OUT/'task-status.json',clean)
        if (status,progress)!=last:
            print(status,progress,flush=True);last=(status,progress)
        if status=='success': break
        if status in ['failed','cancelled']:
            raise RuntimeError(f'Task {status}: {d.get("error_code")} {d.get("error_message","")}')
        time.sleep(8)
    else: raise RuntimeError('Polling soft timeout; resume this same task later')
    downloads=[]
    for name,url in d.get('output',{}).items():
        if not isinstance(url,str) or not url.startswith('https://'): continue
        if not any(s in name for s in ['model','rendered','texture']): continue
        ext='.glb' if 'model' in name else '.png'
        response=requests.get(url,timeout=300);response.raise_for_status()
        if 'model' in name and response.content[:4]!=b'glTF':
            ext='.zip' if response.content[:2]==b'PK' else '.bin'
        p=OUT/(name+ext);p.write_bytes(response.content)
        downloads.append({'kind':name,'file':p.name,'bytes':p.stat().st_size,'sha256':hashlib.sha256(response.content).hexdigest()})
        print('downloaded',name,p.stat().st_size,flush=True)
    state.update(status='downloaded',elapsed_seconds=round(time.time()-state['started_at'],2),downloads=downloads,credits_consumed=d.get('credits_consumed',d.get('consumed_credit')))
    write(statefile,state);print(json.dumps(state),flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--single',action='store_true')
    parser.add_argument('--face-limit',type=int)
    parser.add_argument('--output-name')
    parser.add_argument('--request-baseline')
    parser.add_argument('--dry-run',action='store_true')
    OPTIONS=parser.parse_args()
    SINGLE=OPTIONS.single
    if (OPTIONS.face_limit is not None or OPTIONS.request_baseline) and not OPTIONS.output_name:
        parser.error('Variants require a separate --output-name to preserve historical runs')
    if OPTIONS.face_limit is not None and not 500<=OPTIONS.face_limit<=20000:
        parser.error('This smart-low-poly experiment accepts 500–20000 triangles')
    OUT=HERE/(OPTIONS.output_name or ('05b-tripo' if SINGLE else '05-tripo'))
    try: run()
    except Exception as e:
        print(type(e).__name__+': '+str(e),flush=True);sys.exit(1)
