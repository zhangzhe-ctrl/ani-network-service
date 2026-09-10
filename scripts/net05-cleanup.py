#!/usr/bin/env python3
"""NET-05 product cleanup first; remove owned fixtures only after all are free."""
import argparse
import datetime
import hashlib
import importlib.util
import json
import os
import pathlib
import shutil
import signal
import sys
import time

spec = importlib.util.spec_from_file_location('net05', pathlib.Path(__file__).with_name('net05-kind.py'))
n = importlib.util.module_from_spec(spec); spec.loader.exec_module(n)
s = n.state

def rows(db, query):
    return json.loads(n.sql(db, "SELECT coalesce(json_agg(t),'[]') FROM ("+query+')t;').stdout)

def permissions():
    n.check_permissions()
    a,b=s['tenants']; subnet=s['topology']['a1s1']['id']
    # These negative transactions cannot commit changed business state. The
    # actual runtime role must be stopped by the tenant-preserving FK itself.
    before=rows('network',"SELECT tenant_id,vpc_id,subnet_id FROM network_subnets WHERE subnet_id='%s'"%subnet)
    failure=n.sql('network',"\\set VERBOSITY verbose\nBEGIN; UPDATE network_subnets SET tenant_id='%s' WHERE tenant_id='%s' AND subnet_id='%s'; ROLLBACK;"%(b,a,subnet),role='network',check=False)
    assert failure.returncode!=0 and '23503' in failure.stderr, failure.stderr
    after=rows('network',"SELECT tenant_id,vpc_id,subnet_id FROM network_subnets WHERE subnet_id='%s'"%subnet)
    assert before==after
    instance=next(p['instance_id'] for p in s['probes'].values() if p['tenant']==0)
    query="BEGIN; SELECT set_config('app.current_tenant_id','%s',true); SELECT count(*) FROM workload_instances WHERE tenant_id='%s' AND instance_id='%s'; WITH changed AS (UPDATE workload_instances SET name=name WHERE tenant_id='%s' AND instance_id='%s' RETURNING instance_id) SELECT count(*) FROM changed; ROLLBACK;"%(b,a,instance,a,instance)
    isolation=n.sql('ani',query,role='ani')
    assert isolation.stdout.strip().splitlines()==[b,'0','0'],isolation.stdout
    roles=rows('postgres',"SELECT rolname,rolsuper,rolbypassrls,rolcreatedb,rolcreaterole FROM pg_roles WHERE rolname IN ('network','ani')")
    assert len(roles)==2 and all(not row[k] for row in roles for k in ['rolsuper','rolbypassrls','rolcreatedb','rolcreaterole'])
    n.write('V-02-03-runtime-database-boundaries.json',{'network_foreign_key':{'before':before,'after':after,'exit':failure.returncode,'stderr':failure.stderr},'ani_rls':{'current_tenant':b,'foreign_tenant':a,'select_count':0,'update_count':0},'runtime_roles':roles,'network_rls':False,'network_boundary':'explicit tenant predicates and composite foreign keys, not database RLS'})
    n.event('runtime-tenant-boundaries',status='pass',checks='actual Network runtime FK rejection, ANI runtime RLS read/write denial, separate non-owner roles and RBAC')

def products():
    n.fence()
    assert not list(n.private.glob('hooks-*/*.rule.json')), 'unreleased hook; inspect before cleanup'
    assert not list((n.private/'proxy').glob('*.rule.json')), 'unknown delayed Provider request; inspect before cleanup'
    n.database_snapshot()
    n.delete_probes()
    # Includes every task-created intent, including tombstones and failed setup
    # intents. No unrelated tenant or resource may enter this database fixture.
    ownership={}
    for kind,table,idcol in [('subnets','network_subnets','subnet_id'),('vpcs','network_vpcs','vpc_id')]:
        resources=rows('network','SELECT * FROM '+table+' ORDER BY tenant_id,'+idcol)
        ownership[kind]=[]
        for resource in resources:
            assert resource['tenant_id'] in s['tenants'] and resource['name'].startswith(s['id'])
            tenant=s['tenants'].index(resource['tenant_id'])
            binding=rows('network',"SELECT * FROM network_provider_bindings WHERE tenant_id='%s' AND %s='%s'"%(resource['tenant_id'],idcol,resource[idcol]))[0]
            assert binding['namespace']==s['namespaces'][tenant] and binding['cluster_id']==s['cluster_id']
            ownership[kind].append({'resource':resource,'binding':binding})
            if resource['state']!='deleted':
                n.api('DELETE','/networks/'+kind+'/'+resource[idcol],tenant=tenant,expect=[202])
                n.wait_resource(kind,resource[idcol],tenant,desired='deleted')
            _,current=n.api('GET','/networks/'+kind+'/'+resource[idcol],tenant=tenant,expect=[200])
            assert current['state']=='deleted'
            if kind=='vpcs':assert current['subnet_count']==0
        for ns in s['namespaces']:
            assert not n.get(kind,'-n',ns)['items'], 'Provider CR remains'
    for ns in s['namespaces']:
        for kind in ['vpcs','subnets','vnics','vnicips','eips','pods','deployments','replicasets','services']:
            assert not n.get(kind,'-n',ns)['items'],kind+' remains'
    assert not rows('network',"SELECT attachment_id,state,protocol_blocked FROM network_attachments WHERE state<>'released' OR protocol_blocked")
    assert not rows('network',"SELECT operation_id,state FROM network_operations WHERE state NOT IN ('succeeded','failed')")
    assert not rows('network',"SELECT binding_id,pending_action FROM network_provider_bindings WHERE pending_action<>''")
    assert not rows('ani',"SELECT instance_id,state FROM instance_network_submissions WHERE state<>'closed' OR record->>'PendingRelease'<>'false' OR record->>'IdentityRevoked'<>'true'")
    assert not rows('ani','SELECT id FROM api_keys WHERE revoked_at IS NULL')
    n.database_snapshot(); n.observe()
    n.write('product-resource-ownership-and-cleanup.json',ownership)
    s['product_cleanup_passed']=True;n.save()
    n.event('product-cleanup',status='pass',vpcs=len(ownership['vpcs']),subnets=len(ownership['subnets']),checks='all owner submissions closed, identities revoked, attachments released, actual CR/workload/NIC/IP absence, stable bindings/history/tombstones and zero subnet_count')

def fixtures():
    n.fence()
    assert s.get('product_cleanup_passed'), 'product cleanup must be verified first'
    assert (n.evidence/'final-gates.json').exists(), 'final gate evidence required before deleting recovery inputs'
    gates=json.loads((n.evidence/'final-gates.json').read_text())
    assert gates.get('required_new_gates')=='pass', 'new gate failure leaves recovery inputs intact'
    for ns in s['namespaces']:
        for resource in ['pods','deployments','replicasets','services','secrets','vpcs','subnets','vnics','vnicips','eips']:
            # Secret metadata only, never retrieve a Secret body for evidence.
            remaining=n.kubectl('get',resource,'-n',ns,'-o','name').stdout.strip()
            assert not remaining,(resource,remaining)
    removed=[]
    # All task containers are label-owned; preserve kind, CNI and shared images.
    ids=n.run(['docker','ps','-aq','--filter','label=net05.ani.io/run='+s['id']]).stdout.split()
    for cid in ids:
        detail=json.loads(n.run(['docker','inspect',cid]).stdout)[0]
        assert detail['Config']['Labels']['net05.ani.io/run']==s['id']
        if cid==s['pg_container'][:len(cid)]:continue
        n.run(['docker','rm','-f',cid],timeout=30)
        removed.append({'kind':'container','id':detail['Id'],'name':detail['Name']})
    for key,needle in [('proxy_pid',str(n.private)),('relay_host_pid',s['bridge_gateway'])]:
        if not s.get(key):continue
        pid=s[key]; proc=pathlib.Path('/proc')/str(pid)/'cmdline'
        if proc.exists():
            command=proc.read_bytes().replace(b'\0',b' ').decode()
            assert needle in command and '/ani-network-service-runs/net05-' in command
            os.kill(pid,signal.SIGTERM)
            removed.append({'kind':'process','id':pid,'role':key})
    for fixture in reversed(s['fixtures']):
        n.fence()
        scope=['-n',fixture['namespace']] if fixture.get('namespace') else []
        current=n.get(fixture['kind'],fixture['name'],*scope)
        assert current['metadata']['uid']==fixture['uid'] and current['metadata']['labels']['net05.ani.io/run']==s['id']
        if fixture['kind']=='Namespace':
            assert fixture['name'] in s['namespaces']+[s['control_namespace']]
        # kubectl's raw DELETE forwards the exact UID precondition body.
        version=fixture['apiVersion']
        base='/api/'+version if version=='v1' else '/apis/'+version
        plural={'Namespace':'namespaces','ServiceAccount':'serviceaccounts','Role':'roles','RoleBinding':'rolebindings','ClusterRole':'clusterroles','ClusterRoleBinding':'clusterrolebindings'}[fixture['kind']]
        path=base+('/namespaces/'+fixture['namespace'] if fixture.get('namespace') else '')+'/'+plural+'/'+fixture['name']
        body={'apiVersion':'v1','kind':'DeleteOptions','preconditions':{'uid':fixture['uid']}}
        n.kubectl('delete','--raw='+path,'-f','-',input=json.dumps(body))
        removed.append(fixture)
    n.run(['docker','rm','-f',s['pg_container']],timeout=30)
    removed.append({'kind':'database-container','id':s['pg_container']})
    n.run(['docker','network','rm',s['id']])
    assert not n.run(['docker','ps','-aq','--filter','label=net05.ani.io/run='+s['id']]).stdout.strip()
    for _ in range(60):
        task_ns=[obj for obj in n.get('namespaces')['items'] if obj['metadata']['name'] in s['namespaces']+[s['control_namespace']]]
        if not task_ns:break
        time.sleep(1)
    assert not task_ns
    post=json.loads(n.run(['python3',str(n.root/'scripts/net05-preflight.py')],timeout=180).stdout)
    assert post['status']=='pass'
    n.write('postflight.json',post)
    # Private credentials, env configuration, raw process logs and image build
    # working files belong exclusively to this run and are no longer needed.
    assert n.private.name=='private' and n.private.parent.name.startswith('net05-')
    shutil.rmtree(n.private)
    n.write('fixture-cleanup.json',{'status':'pass','run':s['id'],'removed':removed,'preserved':'original kind/CNI/tools/images/caches and unrelated resources','private_recovery_inputs_removed':True})
    n.event('fixture-cleanup',status='pass',removed=len(removed),private_recovery_inputs_removed=True)

p=argparse.ArgumentParser(description=__doc__);p.add_argument('stage',choices=['permissions','products','fixtures']);args=p.parse_args()
try:
    {'permissions':permissions,'products':products,'fixtures':fixtures}[args.stage]()
except Exception as exc:
    n.event('runner-error',stage='cleanup-'+args.stage,status='fail',error=n.redact(str(exc)));sys.exit(1)
