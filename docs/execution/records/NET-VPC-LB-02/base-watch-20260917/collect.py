"""Independent read-only Watch/API/PG recorder; never updates product state."""
import datetime,json,os,signal,subprocess,threading,time,urllib.request
from pathlib import Path

root=Path.cwd();plan=json.loads(Path('plan.json').read_text())
assert plan['run']=='basewatch-0917'
out=Path('watch-capture');out.mkdir(mode=0o700,exist_ok=False)
stop=threading.Event();lock=threading.Lock();children=[];started=time.monotonic()
def stamp():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def emit(name,data):
    row={'received_at':stamp(),'monotonic_ns':time.monotonic_ns(),**data}
    with lock:
        with (out/name).open('a') as f:f.write(json.dumps(row,separators=(',',':'))+'\n')
def run(cmd,body=None):
    begin=stamp()
    p=subprocess.run(cmd,input=body,text=True,capture_output=True,timeout=10)
    return {'started_at':begin,'command':cmd,'exit':p.returncode,'stdout':p.stdout,'stderr':p.stderr}
def kube(*args):return ['./bin/kubectl','--kubeconfig','kubeconfig.json',*args]
def watch(name,namespace,kind):
    generation=0
    while not stop.is_set():
        generation+=1
        command=kube('-n',namespace,'get',kind,'--watch','--output-watch-events=true','--request-timeout=0','-o','json')
        err=(out/(name+'.stderr.txt')).open('a')
        p=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=err);children.append(p)
        emit(name+'.jsonl',{'record':'watch_start','connection':generation,'command':command,'pid':p.pid})
        buffer='';decoder=json.JSONDecoder()
        try:
            while not stop.is_set():
                chunk=os.read(p.stdout.fileno(),65536)
                if not chunk:break
                buffer+=chunk.decode()
                while buffer.strip():
                    buffer=buffer.lstrip()
                    try:value,end=decoder.raw_decode(buffer)
                    except json.JSONDecodeError:break
                    buffer=buffer[end:]
                    obj=value.get('object',value)
                    if isinstance(obj,dict):obj.get('metadata',{}).pop('managedFields',None)
                    emit(name+'.jsonl',{'record':'event','connection':generation,'event':value})
        finally:
            if p.poll() is None:p.terminate()
            p.wait(timeout=10);err.close()
            emit(name+'.jsonl',{'record':'watch_end','connection':generation,'exit':p.returncode,'intentional':stop.is_set(),'unparsed_bytes':len(buffer)})
        if not stop.wait(1):emit(name+'.jsonl',{'record':'gap','reason':'Watch ended; next kubectl invocation relists; interval is not claimed complete'})

queries={
 'vpcs':'select * from network_vpcs where base_connectivity_required',
 'base':'select * from network_vpc_base_connectivity',
 'eips':'select * from network_eips',
 'snats':'select * from network_snat_bindings',
 'bindings':'select * from network_provider_bindings',
 'reconciliations':'select * from network_reconciliations',
 'operations':'select * from network_operations',
 'history':"select * from network_resource_history where created_at>clock_timestamp()-interval '10 seconds'",
}
sql="SELECT json_build_object('database_at',clock_timestamp(),"+','.join("'%s',(select coalesce(json_agg(t),'[]') from (%s) t)"%(key,q) for key,q in queries.items())+");"
init=json.loads(Path('initialized.json').read_text())
def sample():
    previous=None;first_ready=None;lastmetrics=0
    while not stop.is_set():
        began=time.monotonic()
        try:
            r=run(['docker','exec',init['container'],'psql','-X','-U','postgres','-d',init['database'],'-At','-v','ON_ERROR_STOP=1','-c',sql])
            data=json.loads(r['stdout']) if r['exit']==0 else None
            emit('database.jsonl',{'record':'sample','started_at':r['started_at'],'exit':r['exit'],'data':data,'error':r['stderr']})
            if data and data['vpcs'] and data['base']:
                vpc=data['vpcs'][0];base=data['base'][0]
                request=json.dumps({'tenant_id':plan['tenant_id'],'vpc_id':vpc['vpc_id']})
                r=run(['./bin/lb-api','call','-target','unix://'+plan['sockets']+'/tenant-a.sock','-service','NetworkService','-method','GetVPC'],request)
                emit('api.jsonl',{'record':'sample',**r})
                state=(vpc['state'],base['state'],base['reason'],base['provider_ready'])
                if state!=previous:
                    emit('transitions.jsonl',{'from':previous,'to':state,'database_at':data['database_at'],'vpc_id':vpc['vpc_id']})
                    r=run(kube('--request-timeout=8s','-n',plan['tenant_namespace'],'get','vpcs,eips,snats','-o','json'))
                    emit('direct-at-transition.jsonl',{'record':'independent_get','transition':state,**r})
                    print(json.dumps({'at':stamp(),'state':state}),flush=True)
                    previous=state
                if base['state']=='ready' and first_ready is None:first_ready=time.monotonic()
            if time.monotonic()-lastmetrics>=5:
                listeners=json.loads(Path('listeners.json').read_text())
                with urllib.request.urlopen('http://'+listeners['admin']+'/metrics',timeout=3) as response:
                    lines=response.read().decode().splitlines()
                emit('metrics.jsonl',{'lines':[x for x in lines if 'network_' in x]})
                lastmetrics=time.monotonic()
            if first_ready is not None and time.monotonic()-first_ready>=600:
                emit('lifecycle.jsonl',{'record':'window_complete','seconds_after_first_ready':600});stop.set()
        except Exception as e:
            emit('errors.jsonl',{'error':type(e).__name__+': '+str(e)})
        stop.wait(max(0.01,1-(time.monotonic()-began)))

signal.signal(signal.SIGTERM,lambda *_:stop.set())
signal.signal(signal.SIGINT,lambda *_:stop.set())
emit('lifecycle.jsonl',{'record':'start','run':plan['run'],'source_commit':plan['source_commit'],'pid':os.getpid(),'maximum_seconds':1800,'post_ready_seconds':600})
(out/'query.sql').write_text(sql+'\n')
threads=[]
for name,namespace,kind in [('tenant-vpcs',plan['tenant_namespace'],'vpcs'),('tenant-eips',plan['tenant_namespace'],'eips'),('tenant-snats',plan['tenant_namespace'],'snats'),('platform-vpcs','kcn-system','vpcs'),('platform-subnets','kcn-system','subnets')]:
    t=threading.Thread(target=watch,args=(name,namespace,kind),daemon=True);t.start();threads.append(t)
t=threading.Thread(target=sample,daemon=True);t.start();threads.append(t)
try:
    while not stop.wait(1):
        if time.monotonic()-started>=1800 or (out/'STOP').exists():stop.set()
        if sum(f.stat().st_size for f in out.iterdir() if f.is_file())>150_000_000:
            emit('lifecycle.jsonl',{'record':'size_limit'});stop.set()
finally:
    stop.set()
    for p in children:
        if p.poll() is None:p.terminate()
    for t in threads:t.join(timeout=12)
    emit('lifecycle.jsonl',{'record':'stopped','elapsed_seconds':time.monotonic()-started})
