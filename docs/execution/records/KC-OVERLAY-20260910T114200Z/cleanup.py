"""Delete only this run's explicitly named resources, after ownership checks."""
import run as r

def delete(kind,name,ns=None):
    args=[kind,name]+(['-n',ns] if ns else [])
    out=r.run(r.K+['get']+args+['-o','json'],check=False)
    if out['exit']:
        assert 'NotFound' in out['stderr'],out
        return
    import json
    obj=json.loads(out['stdout'])
    assert obj['metadata'].get('labels',{}).get('runbook.ani.io/run')==r.RUN,obj['metadata']
    r.run(r.K+['delete']+args+['--wait=false'])
    r.wait(kind,name,ns,'delete')
    print('deleted',kind,name,flush=True)

delete('snats',r.SNAT,r.NS)
for name in ['probe-10','probe-11']:
    delete('pods',name,r.NS)
delete('eips',r.EIP,r.NS)
for i in [10,11]:
    delete('subnets',r.RUN+'-subnet-'+str(i),r.NS)
delete('vpcs',r.VPC,r.NS)
delete('subnets',r.PUBLIC,'kcn-system')
delete('eipgateways',r.GW)
r.nat('delete')
delete('namespaces',r.NS)
r.inventory('after')
r.ovn(['show'])
