"""Resumable single model-processing experiment; no automatic paid resubmission."""
import argparse,hashlib,json,sys,time
from pathlib import Path
import requests
from tripo_run import api,write
from glb_preflight import inspect_glb

HERE=Path(__file__).resolve().parent

def budget_gate(out,state,limit):
    checks=[]
    for artifact in state['downloads']:
        if not artifact['file'].endswith('.glb'):continue
        report=inspect_glb(out/artifact['file'],limit)
        name=Path(artifact['file']).stem+'-preflight.json';write(out/name,report)
        checks.append({'report':name,'triangles':report['active_scene_triangles'],'budget_pass':report['budget_pass']})
    (out/'executed-preflight.py').write_bytes((HERE/'glb_preflight.py').read_bytes())
    state['budget_checks']=checks;state['asset_accepted']=False
    write(out/'state.json',state);print('BUDGET_CHECK',json.dumps(checks),flush=True)

def run(config_path):
    cfg=json.loads(config_path.read_text());out=HERE/cfg['output'];out.mkdir(parents=True,exist_ok=True)
    source=HERE/cfg['source_file'];digest=hashlib.sha256(source.read_bytes()).hexdigest()
    assert source.suffix.lower()=='.glb' and source.read_bytes()[:4]==b'glTF'
    params=cfg['parameters'];assert cfg['endpoint']=='/mesh/decimate'
    assert params['model'] in ['v1.0','v2.0'] and params['face_limit']==3500 and params['quad'] is False
    public={'endpoint':cfg['endpoint'],'input_file':cfg['source_file'],'input_sha256':digest,**params}
    fingerprint=hashlib.sha256(json.dumps(public,sort_keys=True).encode()).hexdigest()
    statefile=out/'state.json';state=json.loads(statefile.read_text()) if statefile.exists() else {}
    if state and state['public_request_sha256']!=fingerprint:raise RuntimeError('Existing state belongs to a different request')
    if state.get('status')=='downloaded':
        print('Already downloaded; no new paid request.');budget_gate(out,state,params['face_limit']);return
    if not state.get('task_id'):
        if state.get('submission_started'):raise RuntimeError('Unresolved previous POST; no automatic retry')
        write(out/'request-public.json',public)
        (out/'executed-source.py').write_bytes(Path(__file__).read_bytes())
        (out/'executed-api-helper.py').write_bytes((HERE/'tripo_run.py').read_bytes())
        with source.open('rb') as f:
            uploaded=api('POST','/files',files={'file':(source.name,f,'model/gltf-binary')})
        print('Uploaded model',source.stat().st_size,'bytes',flush=True)
        state={'submission_started':True,'started_at':time.time(),'public_request_sha256':fingerprint}
        write(statefile,state)
        try:task=api('POST',cfg['endpoint'],json={'input':uploaded['file_token'],**params})
        except Exception as e:
            state['submission_error_type']=type(e).__name__;write(statefile,state);raise
        state['task_id']=task['task_id'];write(statefile,state);print('task_id',state['task_id'],flush=True)
    last=None
    for _ in range(180):
        d=api('GET','/tasks/'+state['task_id']);status=d.get('status');progress=d.get('progress')
        clean={k:v for k,v in d.items() if k not in ['output','input']}
        clean['received_parameters']={k:v for k,v in d.get('input',{}).items() if k in ['model','model_version','face_limit','quad','bake']}
        clean['output_keys']=list(d.get('output',{}));write(out/'task-status.json',clean)
        if (status,progress)!=last:print(status,progress,flush=True);last=(status,progress)
        if status=='success':break
        if status in ['failed','cancelled']:
            state.update(status=status,credits_consumed=d.get('credits_consumed'));write(statefile,state)
            raise RuntimeError('Processing task terminated: '+status)
        time.sleep(8)
    else:raise RuntimeError('Soft polling timeout; resume this task, do not create another')
    downloads=[]
    for name,url in d.get('output',{}).items():
        if not isinstance(url,str) or not url.startswith('https://'):continue
        if not any(x in name for x in ['model','rendered','texture']):continue
        response=requests.get(url,timeout=300)
        if response.status_code!=200:raise RuntimeError('Download HTTP '+str(response.status_code))
        blob=response.content
        ext='.glb' if blob[:4]==b'glTF' else '.png' if blob[:8]==b'\x89PNG\r\n\x1a\n' else '.zip' if blob[:2]==b'PK' else '.bin'
        dest=out/(name+ext);dest.write_bytes(blob)
        downloads.append({'kind':name,'file':dest.name,'bytes':len(blob),'sha256':hashlib.sha256(blob).hexdigest()})
        print('Downloaded',dest.name,len(blob),'bytes',flush=True)
    if not any(x['file'].endswith('.glb') for x in downloads):raise RuntimeError('No GLB artifact; task not accepted')
    state.update(status='downloaded',elapsed_seconds=round(time.time()-state['started_at'],2),downloads=downloads,credits_consumed=d.get('credits_consumed'))
    write(statefile,state);budget_gate(out,state,params['face_limit']);print(json.dumps(state),flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('config',type=Path);args=parser.parse_args()
    try:run(args.config)
    except Exception as e:
        print('Processing stopped:',type(e).__name__,str(e) if isinstance(e,RuntimeError) else '(details suppressed to avoid leaking signed URLs)',flush=True)
        sys.exit(1)
