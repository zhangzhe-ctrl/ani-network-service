#!/usr/bin/env python3
"""One bounded, explicitly selected stage per invocation; run only in the test run directory."""
import datetime, ipaddress, json, pathlib, subprocess, sys, time

ROOT = pathlib.Path(__file__).resolve().parent
RUN = 'kceg-0910-1142'
NS = 'tenant-egress-0910-1142'
GW, PUBLIC, VPC, EIP, SNAT = [RUN + '-' + x for x in ['gw','public','vpc','eip','snat']]
NODES = ['kc062-control-plane','kc062-worker','kc062-worker2']
K = ['kubectl','--context=kind-kc062','--request-timeout=15s']
# Imported digest alias was not resolvable by kubelet; verified local tag, Never pull.
IMAGE = 'docker.io/library/net05-1717d354-probe:ffcf0c98acaedd82'
LABEL = {'runbook.ani.io/run': RUN}
seq = len(list(ROOT.glob('command-*.json')))

def save(name, value):
    (ROOT / name).write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n')

def run(args, check=True, timeout=30, input=None):
    global seq
    seq += 1
    start = time.monotonic()
    at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    try:
        p = subprocess.run(args, input=input, capture_output=True, text=True, timeout=timeout)
        rc, out, err = p.returncode, p.stdout, p.stderr
    except subprocess.TimeoutExpired as e:
        rc = 124
        out = e.stdout or ''
        err = e.stderr or ''
        if isinstance(out, bytes): out = out.decode(errors='replace')
        if isinstance(err, bytes): err = err.decode(errors='replace')
    result = dict(at=at, argv=args, exit=rc, elapsed=round(time.monotonic()-start,3), stdout=out, stderr=err)
    save(f'command-{seq:04d}.json', result)
    if check and rc:
        raise RuntimeError(f'command-{seq:04d}: exit={rc}: {out[-1500:]} {err[-1500:]}')
    return result

def get(kind, name=None, ns=None):
    return json.loads(run(K + ['get',kind] + ([name] if name else []) + (['-n',ns] if ns else []) + ['-o','json'])['stdout'])

def cr(kind, name, spec, ns=None):
    return {'apiVersion':'networking.kubercloud.com/v1','kind':kind,'metadata':dict(name=name,labels=LABEL,**({'namespace':ns} if ns else {})),'spec':spec}

def create(obj):
    save('manifest-'+obj['kind'].lower()+'-'+obj['metadata']['name']+'.json', obj)
    data = json.dumps(obj)
    run(K+['create','--dry-run=server','-f','-'],input=data)
    run(K+['create','-f','-'],input=data)
    print('created',obj['kind'],obj['metadata']['name'],flush=True)

def wait(kind, name, ns=None, condition='condition=Ready', seconds=40):
    run(K+['wait',kind+'/'+name,'--for='+condition,'--timeout='+str(seconds)+'s']+(['-n',ns] if ns else []), timeout=seconds+5)

def inventory(tag):
    items={}
    for kind in ['nodes','namespaces','pods','vpcs','subnets','eipgateways','vlannetworks','eips','snats','nats','vnics','vnicips','nics']:
        r=run(K+['get',kind,'-A','-o','custom-columns=NS:.metadata.namespace,NAME:.metadata.name,UID:.metadata.uid','--no-headers'],check=False)
        items[kind]={'exit':r['exit'],'lines':sorted(r['stdout'].splitlines()),'stderr':r['stderr']}
    save(tag+'-inventory.json',items)
    for node in NODES:
        for suffix,cmd in [('nat',['iptables','-t','nat','-S']),('routes',['ip','-4','route'])]:
            r=run(['docker','exec',node]+cmd)
            (ROOT / (tag+'-'+node+'-'+suffix+'.txt')).write_text(r['stdout'])
    save(tag+'-kcn-config.json',get('configmap','kcn-config','kcn-system')['data'])
    run(K+['get','pods','-A','-o','custom-columns=NS:.metadata.namespace,NAME:.metadata.name,PHASE:.status.phase,READY:.status.containerStatuses[*].ready,RESTARTS:.status.containerStatuses[*].restartCount,NODE:.spec.nodeName'])
    run(K+['get','vm,vmi','test-vm-1c1g','-n','default','-o','custom-columns=KIND:.kind,NAME:.metadata.name,UID:.metadata.uid,READY:.status.ready,PHASE:.status.phase,NODE:.status.nodeName'],check=False)
    run(['free','-m'])
    run(['uptime'])
    print(tag,'inventory recorded',flush=True)

def ovn(args):
    return run(K+['exec','-n','kcn-system','kcn-ovn-central-5cfcf4f7b5-dbwnx','-c','ovn-central','--','ovn-nbctl','--timeout=5','--db=tcp:172.18.0.2:6641']+args)

def controls():
    ovn(['show'])
    for node in NODES:
        r=run(['docker','exec',node,'curl','--noproxy','*','--resolve','www.cloudflare.com:443:104.16.124.96','-sS','--connect-timeout','5','--max-time','10','-w','\nhttp_code=%{http_code}\n','https://www.cloudflare.com/cdn-cgi/trace?nonce='+RUN])
        assert 'http_code=200' in r['stdout'] and '\nip=' in r['stdout'],r
    print('OVN read and three node external controls passed',flush=True)

def platform():
    create({'apiVersion':'v1','kind':'Namespace','metadata':{'name':NS,'labels':LABEL}})
    create(cr('EIPGateway',GW,{'scope':'Public','egressType':'Host'}))
    wait('eipgateways',GW)
    create(cr('Subnet',PUBLIC,{'type':'Public','ipVersion':'IPv4','gateway':GW,'cidrBlock':'10.250.200.0/28','gatewayIP':'10.250.200.1','excludeIPs':['10.250.200.1'],'enableDHCP':False,'allowedNamespaces':{'from':'All'}},'kcn-system'))
    wait('subnets',PUBLIC,'kcn-system')
    create(cr('VPC',VPC,{'ipVersion':'IPv4','cidrBlock':'10.241.0.0/16','allowedNamespaces':{'from':'Same'}},NS))
    wait('vpcs',VPC,NS)
    for i in [10,11]:
        create(cr('Subnet',RUN+'-subnet-'+str(i),{'type':'VPC','ipVersion':'IPv4','gateway':VPC,'cidrBlock':f'10.241.{i}.0/24','gatewayIP':f'10.241.{i}.1','enableDHCP':False,'allowedNamespaces':{'from':'Same'}},NS))
        wait('subnets',RUN+'-subnet-'+str(i),NS)
    create(cr('EIP',EIP,{'subnet':'kcn-system/'+PUBLIC,'ipVersion':'IPv4'},NS))
    wait('eips',EIP,NS,'jsonpath={.status.phase}=Available')
    obj=get('eips',EIP,NS)
    addr=obj['spec']['ipAddress']
    assert ipaddress.ip_address(addr) in ipaddress.ip_network('10.250.200.0/28')
    assert not obj['status'].get('boundResource')
    save('eip-address.json',{'ip':addr})
    print('allocated EIP',addr,flush=True)

def pods():
    ca=pathlib.Path('/etc/ssl/certs/ca-certificates.crt').read_text()
    create({'apiVersion':'v1','kind':'ConfigMap','metadata':{'name':RUN+'-public-ca','namespace':NS,'labels':LABEL},'data':{'ca.crt':ca}})
    for i,node in [(10,'kc062-worker'),(11,'kc062-worker2')]:
        name='probe-'+str(i)
        create({'apiVersion':'v1','kind':'Pod','metadata':{'name':name,'namespace':NS,'labels':LABEL,'annotations':{'networking.kubercloud.com/subnet':NS+'/'+RUN+'-subnet-'+str(i)}},'spec':{'nodeName':node,'automountServiceAccountToken':False,'restartPolicy':'Never','hostNetwork':False,'dnsPolicy':'None','dnsConfig':{'nameservers':['1.1.1.1']},'hostAliases':[{'ip':'104.16.124.96','hostnames':['www.cloudflare.com']}],'terminationGracePeriodSeconds':1,'containers':[{'name':'probe','image':IMAGE,'imagePullPolicy':'Never','command':['/probe'],'env':[{'name':'SSL_CERT_FILE','value':'/etc/test-ca/ca.crt'},{'name':'NET05_ID','value':RUN+'-'+name}],'resources':{'requests':{'cpu':'10m','memory':'16Mi'},'limits':{'cpu':'100m','memory':'64Mi'}},'volumeMounts':[{'name':'public-ca','mountPath':'/etc/test-ca','readOnly':True}]}],'volumes':[{'name':'public-ca','configMap':{'name':RUN+'-public-ca'}}]}})
        wait('pod',name,NS)
        obj=get('pod',name,NS)
        assert ipaddress.ip_address(obj['status']['podIP']) in ipaddress.ip_network(f'10.241.{i}.0/24')
        assert obj['spec'].get('hostNetwork',False) is False
        print(name,obj['status']['podIP'],obj['status']['containerStatuses'][0]['imageID'],flush=True)
        run(K+['exec','-n',NS,name,'--','/probe','inspect'])

def nat(action):
    ip=json.loads((ROOT/'eip-address.json').read_text())['ip']
    args=['POSTROUTING','-s',ip+'/32','-o','eth0','-m','comment','--comment',RUN,'-j','MASQUERADE']
    for node in NODES:
        exists=run(['docker','exec',node,'iptables','-t','nat','-C']+args,check=False)['exit']==0
        if action=='add' and not exists:
            run(['docker','exec',node,'iptables','-t','nat','-A']+args)
        elif action=='delete' and exists:
            run(['docker','exec',node,'iptables','-t','nat','-D']+args)
        run(['docker','exec',node,'iptables','-t','nat','-L','POSTROUTING','-n','-v','-x','--line-numbers'])
    print('temporary EIP-only node NAT',action,flush=True)

def probe(stage, expectation):
    results=[]
    for pod in ['probe-10','probe-11']:
        url='https://www.cloudflare.com/cdn-cgi/trace?nonce='+RUN+'-'+stage+'-'+pod
        r=run(K+['exec','-n',NS,pod,'--','/probe','request',url],check=False,timeout=12)
        success=r['exit']==0 and r['stdout'].startswith('status 200\n') and '\nip=' in r['stdout'] and 'h=www.cloudflare.com\n' in r['stdout']
        network_failure=r['exit']!=0 and any(s in r['stdout'] for s in ['dial tcp','Client.Timeout','i/o timeout','network is unreachable'])
        passed=success if expectation=='success' else network_failure
        result={'stage':stage,'pod':pod,'expectation':expectation,'pass':passed,**r}
        save('probe-'+stage+'-'+pod+'.json',result)
        results.append(result)
        print(stage,pod,'pass' if passed else 'FAIL',r['stdout'][:350],flush=True)
    assert all(r['pass'] for r in results),stage

def internal(stage):
    for source,target in [('probe-10','probe-11'),('probe-11','probe-10')]:
        ip=get('pod',target,NS)['status']['podIP']
        r=run(K+['exec','-n',NS,source,'--','/probe','request',f'http://{ip}:18080/?nonce={RUN}-{stage}'])
        assert r['stdout'].startswith('status 200\n') and RUN+'-'+target in r['stdout'] and RUN+'-'+stage in r['stdout']
    print(stage,'bidirectional intra-VPC control passed',flush=True)

def snat(action):
    if action=='create':
        create(cr('Snat',SNAT,{'eip':EIP,'vpc':VPC,'disable':False},NS))
    elif action in ['disable','enable']:
        run(K+['patch','snats',SNAT,'-n',NS,'--type=merge','-p',json.dumps({'spec':{'disable':action=='disable'}})])
    elif action=='delete':
        run(K+['delete','snats',SNAT,'-n',NS,'--wait=false'])
        wait('snats',SNAT,NS,'delete')
        wait('eips',EIP,NS,'jsonpath={.status.phase}=Available')
        return
    wait('snats',SNAT,NS,'condition=Valid')
    wait('snats',SNAT,NS,'jsonpath={.status.phase}='+('Disabled' if action=='disable' else 'Bound'))
    if action!='disable':
        wait('eips',EIP,NS,'jsonpath={.status.phase}=Bound')
    print('snat',action,'state converged',flush=True)

def snapshot(stage):
    for kind,name,ns in [('eipgateways',GW,None),('subnets',PUBLIC,'kcn-system'),('vpcs',VPC,NS),('eips',EIP,NS),('snats',SNAT,NS)]:
        r=run(K+['get',kind,name]+(['-n',ns] if ns else [])+['-o','json'],check=False)
        save(stage+'-'+kind+'.json',r)
    for kind in ['subnets','pods','vnics','vnicips']:
        save(stage+'-tenant-'+kind+'.json',get(kind,ns=NS))
    for node in NODES:
        run(['docker','exec',node,'ip','-4','route'])
        run(['docker','exec',node,'iptables','-t','nat','-L','POSTROUTING','-n','-v','-x','--line-numbers'])
    for kind,name,ns in [('vpcs',VPC,NS),('eipgateways',GW,None)]:
        obj=get(kind,name,ns)
        router=obj['status']['boundResources']['router']
        for cmd in ['lr-nat-list','lr-route-list','lr-policy-list']:
            ovn([cmd,router])
    print(stage,'CR and dataplane snapshot recorded',flush=True)

if __name__=='__main__':
    allowed={'inventory':inventory,'controls':controls,'platform':platform,'pods':pods,'nat':nat,'probe':probe,'internal':internal,'snat':snat,'snapshot':snapshot}
    allowed[sys.argv[1]](*sys.argv[2:])
