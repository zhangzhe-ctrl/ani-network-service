#!/usr/bin/env python3
"""NET-VPC-LB-02-HEALTH platform preparation; execute only on frozen fedora hostname.

Each invocation is one bounded 180-second stage, with no polling loop or mutation
retry. Pending asynchronous prerequisites exit 3; failed/unknown requests exit 1
and retain their planned marker. Existing receipts are reused without replay.
No SQL, host configuration, controller/generated-spec edits or Public EIP/SNAT
traffic is performed. This driver creates only platform product resources and
explicit task-owned qualification Pods; all deletion is identity guarded.

Runtime: merged live-inputs in plan.json plus execution_host, sockets, database.
Required plan.platform:
  intranet={cidr,ovn_gateway_ip,excluded_ips,default_vpc_name,default_vpc_uid,
            intranet_networks}; public={cidr,ovn_gateway_ip,excluded_ips,
            upstream_gateway_ip}; nodes=[two distinct names]; outside_node;
  outside_port; outside_port_preflight={at,node,port,available_at_read};
  dns_name; dns_expected_ip; http_targets=[{url,contains}] (DNS/EG metrics);
  provider_source_revision; provider_source_evidence={path,sha256};
  network_kubeconfig (optional, default runtime/kubeconfig.json).
Provider provenance must be separately reviewed for current runtime images; a
hash-matching file alone is not a source/image derivation proof. HTTP targets
must be numeric addresses inside the declared intranet ranges. No endpoints,
credentials or historical verification are silently filled in by this driver.
Probe image and binary hash are fixed to the reviewed historical fixture.

prepare --step intranet|public-foundation|public-pool|snapshot
qualify --step intranet-pods|public-pods|intranet-evidence|public-evidence|
               intranet-record|public-record|intranet-enable|public-enable|
               intranet-default|public-default
cleanup --step pods|pools|foundation|snapshot

Intranet first admission uses the actual platform prerequisite contract, plus
DNS/HTTP from default-network qualification Pods; it does NOT claim tenant VPC
base-SNAT traffic. Public scope is direct workload egress/return only. Evidence
uses new Pod UIDs, complete instance_id/run/nonce, current pool fingerprint,
current provider images and a new verification timestamp. No 'refresh until
green', historical validity extension or alternative verification scope exists.
"""
import argparse
import datetime as dt
import fcntl
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import time
import uuid
from urllib.parse import urlsplit

PROBE_IMAGE = 'localhost/lb02-2b3122-probe@sha256:647c2acd8e115511a18506014995ec01b7d0d62fbc05f2a6e51a5c65c2a3fcce'
PROBE_HASH = 'ffcf0c98acaedd82d52d8b9b9f981a8bbc8b1fbc4499be94947d9040f0014bed'
STEPS = {'prepare': {'intranet', 'public-foundation', 'public-pool', 'snapshot'},
         'qualify': {s+'-'+x for s in ('intranet', 'public') for x in ('pods', 'evidence', 'record', 'enable', 'default')},
         'cleanup': {'pods', 'pools', 'foundation', 'snapshot'}}
KINDS = {'intranet': ('IntranetAddressPool', 'pool_id'), 'public': ('PublicAddressPool', 'pool_id'),
         'vlan': ('VlanNetwork', 'vlan_network_id'), 'gateway': ('EgressGateway', 'gateway_id')}

class Pending(Exception): pass

def now(): return dt.datetime.now(dt.timezone.utc).isoformat()
def encode(x): return (json.dumps(x, sort_keys=True, indent=2)+'\n').encode()
def digest(x): return hashlib.sha256(encode(x)).hexdigest()
def require(v, message):
    if not v: raise RuntimeError(message)
def exclusive(p, x):
    with os.fdopen(os.open(p, os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600), 'wb') as f:
        f.write(encode(x)); f.flush(); os.fsync(f.fileno())
def atomic(p, x):
    q=p.with_name(p.name+'.'+uuid.uuid4().hex+'.tmp'); exclusive(q,x); q.replace(p)
def parsed_time(t): return dt.datetime.fromisoformat(t.replace('Z','+00:00'))
def fresh_resource(v):
    return v.get('state') == 'RESOURCE_STATE_AVAILABLE' and not v.get('observation_stale', True) and not v.get('reason')
def conditions(o, *types):
    cs={c['type']:c for c in o.get('status',{}).get('conditions',[])}
    return not o.get('metadata',{}).get('deletionTimestamp') and o.get('status',{}).get('observedGeneration') == o['metadata'].get('generation') and all(cs.get(t,{}).get('status')=='True' for t in types)

def ipv4(s): return str(ipaddress.IPv4Address(s))
def covers(networks, target):
    t=ipaddress.ip_network(target)
    return any(t.subnet_of(ipaddress.ip_network(n)) for n in networks)
def ipv4_list(raw):
    # Accept only the actual config's simple JSON or YAML sequence of IPv4 CIDRs.
    try: values=json.loads(raw)
    except json.JSONDecodeError:
        lines=[x.strip() for x in raw.splitlines() if x.strip()]
        require(all(x.startswith('- ') for x in lines), 'unrecognized intranetNetworks format; do not guess')
        values=[x[2:].strip().strip('\"\'') for x in lines]
    require(isinstance(values,list) and values, 'empty intranetNetworks')
    for v in values:
        n=ipaddress.ip_network(v); require(n.version==4 and n.prefixlen>0 and str(n)==v, 'invalid/overbroad intranetNetworks')
    return values

class Driver:
    def __init__(self,a):
        self.runtime=Path(a.runtime).resolve(strict=True); self.plan=json.loads((self.runtime/'plan.json').read_text()); p=self.plan
        require(p['task']=='NET-VPC-LB-02-HEALTH' and p['execution_alias']=='fedora', 'wrong task/host alias')
        require(socket.gethostname()==p['execution_host'], 'not the frozen fedora hostname')
        require(p['cluster_uid']=='be57b911-892c-4e75-aa9d-4a05d819c59e', 'wrong expected cluster')
        require(self.runtime.stat().st_uid==os.getuid() and self.runtime.stat().st_mode&0o077==0, 'runtime must be private/caller owned')
        self.cfg=p['platform']; self.phase=a.phase; self.step=a.step; self.deadline=time.monotonic()+180
        self.lock=open(self.runtime/'platform-driver.lock','a+'); fcntl.flock(self.lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        self.root=self.runtime/'platform-driver'; self.root.mkdir(mode=0o700,exist_ok=True)
        self.calls=self.root/'calls'; self.calls.mkdir(mode=0o700,exist_ok=True)
        self.actions=self.root/'actions'; self.actions.mkdir(mode=0o700,exist_ok=True)
        self.state_path=self.root/'state.json'
        if not self.state_path.exists(): exclusive(self.state_path,{'task':p['task'],'run':p['live_run'],'resources':{},'pods':{},'evidence':{}})
        self.state=json.loads(self.state_path.read_text()); require(self.state['run']==p['live_run'],'state belongs to another run')
        self.api=self.runtime/'bin/lb-api'; self.kubectl=self.runtime/'bin/kubectl'; self.owner_config=self.runtime/'owner-kubeconfig.json'
        self.network_config=Path(self.cfg.get('network_kubeconfig',str(self.runtime/'kubeconfig.json')))
        self.sock=str(Path(p['sockets']).resolve(strict=True)/'platform.sock'); require(len(self.sock.encode())<=107,'socket path exceeds budget')
        self.fixtures={x['role']:x for x in p['platform_fixture_names']}
        require(len(self.cfg['nodes'])==2 and len(set(self.cfg['nodes']))==2,'two distinct qualification nodes required')
        require(self.cfg['outside_node'] not in self.cfg['nodes'],'outside observer must use third node')
        require(isinstance(self.cfg['outside_port'],int) and 1024<self.cfg['outside_port']<65536,'invalid dedicated outside port')
        for x in self.fixtures.values():
            require(x['namespace']==p['management_namespace'] and x['pod_name'].startswith(p['live_run']+'-'),'fixture outside task namespace')
            uuid.UUID(x['instance_id'])
        exclusive(self.call_path('invocation'),{'at':now(),'phase':self.phase,'step':self.step,'maximum_seconds':180,'plan_sha256':digest(p)})
        ns=self.kube(['get','namespace','kube-system','-o','json'],network=True)
        require(ns['metadata']['uid']==p['cluster_uid'],'actual cluster UID mismatch')
    def call_path(self,label): return self.calls/('%06d-%s.json'%(len(list(self.calls.iterdir()))+1,label))
    def save(self): atomic(self.state_path,self.state)
    def execute(self,label,command,body=None,timeout=25):
        remaining=self.deadline-time.monotonic(); require(remaining>0,'fixed stage deadline reached')
        entry={'at':now(),'phase':self.phase,'step':self.step,'command':command,'request':body}; path=self.call_path(label)
        try:
            r=subprocess.run(command,input=None if body is None else json.dumps(body),text=True,capture_output=True,timeout=min(timeout,remaining))
            entry.update(exit=r.returncode,stdout=r.stdout,stderr=r.stderr,completed_at=now())
        except subprocess.TimeoutExpired as e:
            entry.update(exit=None,timeout=True,completed_at=now(),stdout=str(e.stdout or ''),stderr=str(e.stderr or '')); exclusive(path,entry)
            raise RuntimeError('request outcome unknown; preserve '+str(path)) from None
        exclusive(path,entry); require(r.returncode==0,'request failed; no retry; inspect '+str(path)); return r.stdout
    def mutation(self,key,intent,fn):
        planned=self.actions/(key+'.planned.json'); receipt=self.actions/(key+'.receipt.json')
        if planned.exists():
            require(json.loads(planned.read_text())['intent']==intent,'changed mutation intent '+key)
            require(receipt.exists(),'unresolved earlier mutation; manual review required '+key)
            return json.loads(receipt.read_text())['result']
        exclusive(planned,{'at':now(),'intent':intent}); result=fn(); exclusive(receipt,{'at':now(),'result':result}); return result
    def rpc(self,method,request,key=None):
        def call():
            raw=self.execute(method,[str(self.api),'call','-target','unix://'+self.sock,'-service','PlatformNetworkService','-method',method],request)
            envelope=json.loads(raw); require(envelope.get('code')=='OK' and isinstance(envelope.get('response'),dict),'bad RPC response envelope')
            return envelope['response']
        return call() if key is None else self.mutation(key,{'method':method,'request':request},call)
    def kube_command(self,args,network=False):
        return [str(self.kubectl),'--kubeconfig',str(self.network_config if network else self.owner_config),'--request-timeout=20s',*args]
    def kube(self,args,body=None,key=None,network=False,raw=False):
        command=self.kube_command(args,network)
        def call():
            out=self.execute('kubectl-'+args[0],command,body)
            return out if raw else json.loads(out) if out.strip() else None
        return call() if key is None else self.mutation(key,{'command':command,'body':body},call)
    def remember(self,key,v):
        require(v['id'] and v['cluster_id']==self.plan['cluster_id'],'platform placement differs')
        if key in self.state['resources']: require(self.state['resources'][key]['id']==v['id'],'platform identity changed')
        require(v['name']==self.plan['display_names'][{'intranet':'intranet_pool','public':'public_pool','vlan':'public_vlan','gateway':'public_gateway'}[key]],'unexpected accepted name')
        self.state['resources'][key]=v; self.save(); return v
    def get(self,key):
        v=self.state['resources'].get(key); require(v is not None,'missing accepted platform resource '+key)
        kind,field=KINDS[key]; return self.remember(key,self.rpc('Get'+kind,{field:v['id']})['resource'])
    def ready(self,key):
        v=self.get(key)
        if not fresh_resource(v): raise Pending(key+' not fresh/available; stopped after one GET')
        return v
    def pool(self,key):
        v=self.ready(key); return v,v['intranet_pool' if key=='intranet' else 'pool']
    def provenance(self,pool):
        rev=self.cfg['provider_source_revision']; require(re.fullmatch('[0-9a-f]{40}',rev),'exact provider source revision required')
        src=self.cfg['provider_source_evidence']; path=Path(src['path'])
        require(hashlib.sha256(path.read_bytes()).hexdigest()==src['sha256'],'provider provenance file hash mismatch')
        origin=json.loads(path.read_text())['kc']
        require(origin['resolved_commit']==rev and origin['running_image_id']==self.plan['images']['kc'],'historical source mapping not for current immutable image')
        require(pool['observed_provider_images']==[self.plan['images']['kc']],'provider pool images differ from frozen installation')
        return {'provider_source_revision':rev,'provider_image_digests':pool['observed_provider_images'],'source_evidence':src}
    def provider_pool(self,key):
        v,cfg=self.pool(key)
        values=self.kube(['get','subnets.networking.kubercloud.com','-n','kcn-system','-o','json'],network=True)['items']
        found=[x for x in values if x['metadata'].get('labels',{}).get('network.ani.io/resource-id')==v['id']]
        require(len(found)==1,'new pool must have one exact product-owned Provider Subnet'); o=found[0]
        require(o['metadata']['labels'].get('network.ani.io/managed-by')=='ani-network-service','Provider owner differs')
        require(conditions(o,'Valid','Initialized','Ready'),'Provider pool current conditions/generation not ready')
        recorded=self.state.setdefault('provider',{}).get(key)
        if recorded: require(o['metadata']['uid']==recorded['uid'],'pool Provider UID replaced')
        self.state['provider'][key]={'name':o['metadata']['name'],'namespace':'kcn-system','uid':o['metadata']['uid']}; self.save()
        require(o['spec']['cidrBlock']==cfg['cidr'] and o['spec']['gatewayIP']==cfg['ovn_gateway_ip'],'pool address mapping differs')
        return v,cfg,o
    def prepare(self):
        p,n=self.cfg,self.plan['display_names']
        if self.step=='intranet':
            body=dict(p['intranet'],name=n['intranet_pool'],description='NET-VPC-LB-02-HEALTH isolated Intranet qualification',idempotency_key=self.plan['live_run']+'-intranet')
            self.remember('intranet',self.rpc('CreateIntranetAddressPool',body,'create-intranet')['resource'])
        elif self.step=='public-foundation':
            device=self.rpc('GetNetworkDevice',{'device_id':self.plan['retained_device']['device_id']})['resource']
            if not fresh_resource(device): raise Pending('retained device not currently fresh/available')
            self.remember('vlan',self.rpc('CreateVlanNetwork',{'name':n['public_vlan'],'device_id':device['id'],'vlan_id':0,'idempotency_key':self.plan['live_run']+'-vlan'},'create-vlan')['resource'])
            self.remember('gateway',self.rpc('CreateEgressGateway',{'name':n['public_gateway'],'idempotency_key':self.plan['live_run']+'-gateway'},'create-gateway')['resource'])
        elif self.step=='public-pool':
            vlan,gateway=self.ready('vlan'),self.ready('gateway')
            body=dict(p['public'],name=n['public_pool'],mode='PUBLIC_POOL_MODE_UNDERLAY',gateway_id=gateway['id'],vlan_network_id=vlan['id'],idempotency_key=self.plan['live_run']+'-public')
            self.remember('public',self.rpc('CreatePublicAddressPool',body,'create-public')['resource'])
        else: self.snapshot()
    def create_pods(self,key):
        v,cfg,pool=self.provider_pool(key)
        require(not cfg['allocation_enabled'],'qualification starts with new pool allocation disabled')
        roles=['intranet-a','intranet-b'] if key=='intranet' else ['public-a','public-b','outside']
        if key=='public':
            check=self.cfg['outside_port_preflight']
            require(check['node']==self.cfg['outside_node'] and check['port']==self.cfg['outside_port'] and check['available_at_read'] is True,'outside dedicated port has no clean read-only preflight')
            require(dt.timedelta(0)<=dt.datetime.now(dt.timezone.utc)-parsed_time(check['at'])<dt.timedelta(minutes=30),'outside port preflight stale; refresh listener read before creating fixture')
        for i,role in enumerate(roles):
            item=self.fixtures[role]; outside=role=='outside'; port=self.cfg['outside_port'] if outside else 8080
            labels={'network.ani.io/test-run':self.plan['live_run'],'network.ani.io/instance-id':item['instance_id'],'network.ani.io/fixture-scope':'platform-'+key+'-qualification'}
            spec={'automountServiceAccountToken':False,'restartPolicy':'Always','nodeSelector':{'kubernetes.io/hostname':self.cfg['outside_node'] if outside else self.cfg['nodes'][i]},'securityContext':{'runAsNonRoot':True,'runAsUser':65532,'runAsGroup':65532,'seccompProfile':{'type':'RuntimeDefault'}},'containers':[{'name':'probe','image':PROBE_IMAGE,'imagePullPolicy':'Never','env':[{'name':'NET05_ID','value':self.plan['live_run']},{'name':'ANI_WORKLOAD_ID','value':item['instance_id']},{'name':'NET05_PORT','value':str(port)}],'ports':[{'containerPort':port}],'resources':{'requests':{'cpu':'10m','memory':'32Mi'},'limits':{'cpu':'100m','memory':'64Mi'}},'securityContext':{'allowPrivilegeEscalation':False,'readOnlyRootFilesystem':True,'capabilities':{'drop':['ALL']}}}]}
            meta={'name':item['pod_name'],'namespace':item['namespace'],'labels':labels}
            if key=='public' and not outside: meta['annotations']={'networking.kubercloud.com/subnet':'kcn-system/'+pool['metadata']['name']}
            if outside: spec.update(hostNetwork=True,dnsPolicy='ClusterFirstWithHostNet')
            result=self.kube(['create','-f','-','-o','json'],{'apiVersion':'v1','kind':'Pod','metadata':meta,'spec':spec},'create-pod-'+role)
            require(result['metadata']['namespace']==item['namespace'] and result['metadata']['uid'],'missing Pod creation identity')
            self.state['pods'][role]={'uid':result['metadata']['uid'],'name':item['pod_name'],'namespace':item['namespace'],'instance_id':item['instance_id']}; self.save()
    def pod(self,role,absent=False):
        record=self.state['pods'].get(role); require(record is not None,'no Pod receipt '+role)
        args=['get','pod',record['name'],'-n',record['namespace'],'-o','json']
        if absent: args.append('--ignore-not-found')
        o=self.kube(args)
        if o is None: return None
        m=o['metadata']; require(m['uid']==record['uid'] and not m.get('ownerReferences'),'Pod UID or owner changed')
        require(m.get('labels',{}).get('network.ani.io/test-run')==self.plan['live_run'] and m['labels'].get('network.ani.io/instance-id')==record['instance_id'],'Pod task/instance differs')
        return o
    def exec_args(self,role,argv):
        p=self.state['pods'][role]; return ['exec','-n',p['namespace'],p['name'],'-c','probe','--',*argv]
    def inspect_pods(self,roles):
        values={}
        for role in roles:
            o=self.pod(role)
            if o.get('status',{}).get('phase')!='Running' or not o.get('status',{}).get('podIP'): raise Pending(role+' not running/addressed')
            result=self.kube(self.exec_args(role,['sha256sum','/probe']),raw=True)
            require(result.split()[0]==PROBE_HASH,'executed probe binary identity differs')
            values[role]=o
        return values
    def http(self,client,server,address,port):
        nonce='obs-'+uuid.uuid4().hex; url='http://'+ipv4(address)+':'+str(port)+'/?nonce='+nonce
        raw=self.kube(self.exec_args(client,['/probe','request',url]),raw=True)
        require(raw.startswith('status 200\n'),'direct HTTP status failed')
        result=json.loads(raw.split('\n',1)[1]); item=self.fixtures[server]
        require(result.get('fixture_id')==self.plan['live_run'] and result.get('instance_id')==item['instance_id'] and result.get('nonce')==nonce,'complete HTTP run/instance/nonce mismatch')
        return {'client':client,'server':server,'destination':address,'nonce':nonce,'response':result,'result':'pass'}
    def peer_source(self,client,server,destination,expected):
        # One held HTTP connection, one receiver socket snapshot. No retry loop.
        nonce='obs-src-'+uuid.uuid4().hex; destination=ipv4(destination); expected=ipv4(expected); port=self.cfg['outside_port']
        shell="exec 3<>/dev/tcp/"+destination+"/"+str(port)+"; printf 'GET /?nonce="+nonce+" HTTP/1.1\\r\\nHost: fixture\\r\\n\\r\\n' >&3; /usr/bin/timeout 6 cat <&3; rc=$?; if [ \"$rc\" -eq 124 ]; then exit 0; fi; exit \"$rc\""
        cmd=self.kube_command(self.exec_args(client,['/usr/bin/timeout','12','/usr/bin/bash','-c',shell]))
        require(self.deadline-time.monotonic()>30,'insufficient stage budget for source observation')
        evidence={'at':now(),'client_command':cmd,'expected_source':expected,'nonce':nonce}
        proc=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        evidence['driver_child_pid']=proc.pid
        try:
            time.sleep(1)
            raw=self.kube(self.exec_args(server,['cat','/proc/net/tcp','/proc/net/tcp6']),raw=True)
            peers=[]
            def addr(h):
                b=bytes.fromhex(h); b=b''.join(b[i:i+4][::-1] for i in range(0,len(b),4)); ip=ipaddress.ip_address(b)
                return str(ip.ipv4_mapped or ip) if ip.version==6 else str(ip)
            for line in raw.splitlines():
                f=line.split()
                if len(f)<4 or f[3]!='01': continue
                local,lp=f[1].split(':'); peer,pp=f[2].split(':')
                if int(lp,16)==port: peers.append({'local':addr(local),'peer':addr(peer),'peer_port':int(pp,16)})
            stdout,stderr=proc.communicate(timeout=15); evidence.update(exit=proc.returncode,stdout=stdout,stderr=stderr,receiver_peers=peers)
            body=stdout.split('\r\n\r\n',1)[-1] if '\r\n\r\n' in stdout else stdout.split('\n\n',1)[-1]
            result=json.loads(body.strip()); evidence['http_identity_pass']=proc.returncode==0 and '200 OK' in stdout.splitlines()[0] and result.get('fixture_id')==self.plan['live_run'] and result.get('instance_id')==self.fixtures[server]['instance_id'] and result.get('nonce')==nonce
            evidence['receiver_source_pass']=any(x['peer']==expected and x['local']==destination for x in peers)
        except BaseException as e:
            proc.kill(); stdout,stderr=proc.communicate(); evidence.update(error=str(e),stdout=stdout,stderr=stderr)
            exclusive(self.call_path('source-address'),evidence); raise
        exclusive(self.call_path('source-address'),evidence)
        require(evidence['http_identity_pass'] and evidence['receiver_source_pass'],'bounded source-address proof failed; no retry')
        return evidence
    def intranet_contract(self,cfg,pool):
        vpc=self.kube(['get','vpcs.networking.kubercloud.com',cfg['default_vpc_name'],'-n','kcn-system','-o','json'],network=True)
        require(vpc['metadata']['uid']==cfg['default_vpc_uid'] and conditions(vpc,'Valid','Initialized','Ready'),'default VPC identity/conditions differ')
        require(pool['spec'].get('type')=='Intranet' and pool['spec'].get('gateway')=='kcn-system/'+cfg['default_vpc_name'],'Intranet pool gateway mapping differs')
        cm=self.kube(['get','configmap','kcn-config','-n','kcn-system','-o','json'],network=True)
        require(cm['metadata']['uid']==self.plan['retained_device']['kcn_config_uid'],'kcn-config UID differs')
        ranges=ipv4_list(cm['data']['intranetNetworks']); declared=cfg['intranet_networks']
        require(all(covers(ranges,x) for x in declared),'declared ranges not configured')
        services=self.kube(['get','servicecidrs.networking.k8s.io','-o','json'],network=True)['items']; require(services,'no ServiceCIDR facts')
        for item in services:
            for cidr in item['spec']['cidrs']: require(covers(ranges,cidr) and covers(declared,cidr),'ServiceCIDR not covered')
        pods=self.kube(['get','pods','-n','kcn-system','-o','json'],network=True)['items']; roles={'controller','cni-ds','ovs-ds','ovn-central'}; seen=set()
        for pod in pods:
            role=pod['metadata'].get('labels',{}).get('networking.kubercloud.com/app')
            if role not in roles: continue
            require(pod.get('status',{}).get('phase')=='Running' and all(c.get('ready') and c.get('imageID')==self.plan['images']['kc'] for c in pod.get('status',{}).get('containerStatuses',[])) and pod.get('status',{}).get('containerStatuses'),'provider component unhealthy or image drift')
            seen.add(role)
            if role=='controller':
                found=False
                for c in pod['spec']['containers']:
                    cmd=c.get('command',[]); args=c.get('args',[]); tokens=cmd+args
                    if not any('controller' in x for x in cmd) and 'controller' not in args: continue
                    found=True; router='kcn-cluster'
                    for i,t in enumerate(tokens):
                        if t.startswith('--cluster-router='): router=t.split('=',1)[1]
                        if t=='--cluster-router': router=tokens[i+1]
                    require(router==cfg['default_vpc_name'],'controller default router differs')
                require(found,'controller executable identity missing')
        require(seen==roles,'missing provider role evidence')
        return {'default_vpc_uid':vpc['metadata']['uid'],'pool_uid':pool['metadata']['uid'],'configured_ranges':ranges,'declared_ranges':declared,'provider_roles':sorted(seen),'result':'pass_for_platform_contract_prerequisites'}
    def evidence(self,key):
        evidence_path=self.root/(key+'-qualification.json')
        require(not evidence_path.exists(),'qualification already attempted; same evidence cannot be rerun or refreshed')
        v,cfg,pool=self.provider_pool(key); proof={'at':now(),'pool_id':v['id'],'topology_fingerprint':cfg['topology_fingerprint'],'provider_uid':pool['metadata']['uid'],**self.provenance(cfg),'status':'started','traffic':[]}
        exclusive(evidence_path.with_suffix('.planned.json'),proof)
        try:
            if key=='intranet':
                proof['contract']=self.intranet_contract(cfg,pool); actual=self.inspect_pods(['intranet-a','intranet-b']); proof['pods']=actual
                for role in actual:
                    text=self.kube(self.exec_args(role,['getent','hosts',self.cfg['dns_name']]),raw=True)
                    require(self.cfg['dns_expected_ip'] in {line.split()[0] for line in text.splitlines() if line.split()},'DNS result differs')
                    for target in self.cfg['http_targets']:
                        u=urlsplit(target['url']); require(u.scheme=='http' and u.username is None and u.password is None,'unsafe qualification URL')
                        addr=ipv4(u.hostname); require(covers(cfg['intranet_networks'],addr+'/32'),'HTTP target outside declared intranet')
                        raw=self.kube(self.exec_args(role,['/probe','request',target['url']]),raw=True)
                        require(raw.startswith('status 200\n') and target['contains'] in raw,'platform HTTP qualification failed')
                        proof['traffic'].append({'client':role,'url':target['url'],'result':'pass'})
                require(self.cfg['http_targets'],'no configured platform HTTP targets')
                proof.update(scope='base_intranet',limitations=['default-network platform probes do not prove tenant VPC base EIP/SNAT path','Public traffic not verified'])
            else:
                actual=self.inspect_pods(['public-a','public-b','outside']); proof['pods']=actual
                addresses={role:ipv4(o['status']['podIP']) for role,o in actual.items()}
                require(all(ipaddress.ip_address(addresses[r]) in ipaddress.ip_network(cfg['cidr']) for r in ('public-a','public-b')),'Public fixture not in new pool')
                require(len(set(addresses.values()))==3,'fixture addresses overlap')
                for role in actual: proof['traffic'].append(self.http(role,role,'127.0.0.1',self.cfg['outside_port'] if role=='outside' else 8080))
                for role in ('public-a','public-b'):
                    proof['traffic'].append(self.http(role,'outside',addresses['outside'],self.cfg['outside_port']))
                    proof['traffic'].append(self.http('outside',role,addresses[role],8080))
                    proof['traffic'].append(self.peer_source(role,'outside',addresses['outside'],addresses[role]))
                proof['traffic'].append(self.http('public-a','public-b',addresses['public-b'],8080)); proof['traffic'].append(self.http('public-b','public-a',addresses['public-a'],8080))
                proof.update(scope='underlay_lab_direct_workload_egress_return',limitations=['EIP ingress not verified','tenant Public SNAT egress/source translation not verified','Internet and production Underlay not verified'])
            # The same Provider identity/fingerprint must survive actual qualification.
            end,latest=self.pool(key); require(latest['topology_fingerprint']==proof['topology_fingerprint'] and latest['observed_provider_images']==proof['provider_image_digests'],'topology/provider changed during qualification')
            proof.update(status='pass',verified_at=now())
        except BaseException as e:
            proof.update(status='fail',reason=str(e),completed_at=now()); exclusive(evidence_path,proof); raise
        exclusive(evidence_path,proof); self.state['evidence'][key]={'path':str(evidence_path),'sha256':hashlib.sha256(evidence_path.read_bytes()).hexdigest()}; self.save()
    def qualify(self):
        key,stage=self.step.split('-',1)
        if stage=='pods': self.create_pods(key); return
        if stage=='evidence': self.evidence(key); return
        v,cfg=self.pool(key); kind='Intranet' if key=='intranet' else 'Public'
        if stage=='record':
            receipt=self.state['evidence'].get(key); require(receipt is not None,'no successful real qualification')
            path=Path(receipt['path']); require(hashlib.sha256(path.read_bytes()).hexdigest()==receipt['sha256'],'qualification evidence mutated')
            evidence=json.loads(path.read_text()); require(evidence['status']=='pass' and evidence['pool_id']==v['id'],'no applicable pass evidence')
            require(evidence['topology_fingerprint']==cfg['topology_fingerprint'] and evidence['provider_image_digests']==cfg['observed_provider_images'],'evidence no longer matches pool')
            verified=parsed_time(evidence['verified_at']); expires=verified+dt.timedelta(hours=2)
            require(expires>dt.datetime.now(dt.timezone.utc),'qualification expired; do not refresh timestamp')
            body={'pool_id':v['id'],'expected_version':v['version'],'idempotency_key':self.plan['live_run']+'-'+key+'-verify','verification':{'provider_source_revision':evidence['provider_source_revision'],'provider_image_digests':evidence['provider_image_digests'],'topology_fingerprint':evidence['topology_fingerprint'],'evidence_reference':'NET-VPC-LB-02-HEALTH/'+path.name+' sha256:'+receipt['sha256'],'scope':evidence['scope'],'verified_at':evidence['verified_at'],'expires_at':expires.isoformat()}}
            self.remember(key,self.rpc('Record'+kind+'PoolVerification',body,key+'-verify')['resource'])
        elif stage=='enable':
            self.remember(key,self.rpc('Set'+kind+'PoolAllocationEnabled',{'pool_id':v['id'],'enabled':True,'expected_version':v['version'],'idempotency_key':self.plan['live_run']+'-'+key+'-enable'},key+'-enable')['resource'])
        elif stage=='default':
            require(cfg['allocation_enabled'],'allocation not enabled')
            self.remember(key,self.rpc('SetDefault'+kind+'Pool',{'pool_id':v['id'],'expected_version':v['version'],'idempotency_key':self.plan['live_run']+'-'+key+'-default'},key+'-default')['resource'])
    def cleanup(self):
        # Preserve unknown POST outcomes; only exact accepted receipt IDs are owned.
        for marker in self.actions.glob('create-*.planned.json'):
            require(marker.with_name(marker.name.replace('.planned.','.receipt.')).exists(),'unresolved create blocks automatic cleanup '+marker.name)
        for key in KINDS:
            receipt=self.actions/('create-'+key+'.receipt.json')
            if key not in self.state['resources'] and receipt.exists(): self.remember(key,json.loads(receipt.read_text())['result']['resource'])
        for role,item in self.fixtures.items():
            receipt=self.actions/('create-pod-'+role+'.receipt.json')
            if role not in self.state['pods'] and receipt.exists():
                o=json.loads(receipt.read_text())['result']; self.state['pods'][role]={'uid':o['metadata']['uid'],'name':item['pod_name'],'namespace':item['namespace'],'instance_id':item['instance_id']}; self.save()
        if self.step=='snapshot': self.snapshot(); return
        if self.step=='pods':
            for role in self.state['pods']:
                o=self.pod(role,absent=True)
                if o is None: continue
                m=o['metadata']; uri='/api/v1/namespaces/'+m['namespace']+'/pods/'+m['name']
                self.kube(['delete','--raw',uri,'-f','-'],{'apiVersion':'v1','kind':'DeleteOptions','preconditions':{'uid':m['uid']},'gracePeriodSeconds':30,'propagationPolicy':'Foreground'},'delete-pod-'+role)
            return
        for role in self.state['pods']:
            if self.pod(role,absent=True) is not None: raise Pending('qualification Pod still exists; do not delete pools')
        if self.step=='pools':
            for key in ('public','intranet'):
                if key not in self.state['resources']: continue
                v=self.get(key)
                if v['state']=='RESOURCE_STATE_DELETED': continue
                cfg=v['pool' if key=='public' else 'intranet_pool']; kind='Public' if key=='public' else 'Intranet'
                if cfg['allocation_enabled']:
                    v=self.remember(key,self.rpc('Set'+kind+'PoolAllocationEnabled',{'pool_id':v['id'],'enabled':False,'expected_version':v['version'],'idempotency_key':self.plan['live_run']+'-'+key+'-disable'},key+'-disable')['resource'])
                self.remember(key,self.rpc('Delete'+kind+'AddressPool',{'pool_id':v['id']},'delete-'+key)['resource'])
        elif self.step=='foundation':
            for key in ('public','intranet'):
                if key in self.state['resources'] and self.get(key)['state']!='RESOURCE_STATE_DELETED': raise Pending('pool not deleted; preserve gateway/VLAN')
            for key in ('gateway','vlan'):
                if key not in self.state['resources']: continue
                v=self.get(key)
                if v['state']=='RESOURCE_STATE_DELETED': continue
                kind,field=KINDS[key]; self.remember(key,self.rpc('Delete'+kind,{field:v['id']},'delete-'+key)['resource'])
    def snapshot(self):
        for key in list(self.state['resources']): self.get(key)
        for role in self.state['pods']: self.pod(role,absent=True)
        self.rpc('GetPlatformNetworkCapabilities',{})

def main():
    os.umask(0o077); parser=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('phase',choices=STEPS); parser.add_argument('--step',required=True)
    parser.add_argument('--runtime',default='/home/chabking/workspace/ani-network-service-runs/net-lb-obs-01-20260916T005807Z-baseline/private/runtime')
    a=parser.parse_args(); require(a.step in STEPS[a.phase],'unsupported explicit stage')
    try:
        d=Driver(a); getattr(d,a.phase)(); print(json.dumps({'result':'pass','phase':a.phase,'step':a.step,'state':str(d.state_path)})); return 0
    except Pending as e: print(json.dumps({'result':'not_verified','phase':a.phase,'step':a.step,'reason':str(e)})); return 3
    except Exception as e: print(json.dumps({'result':'fail','phase':a.phase,'step':a.step,'reason':str(e)})); return 1
if __name__=='__main__': sys.exit(main())
