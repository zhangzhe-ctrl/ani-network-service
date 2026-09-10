"""Diagnostic override of this run's empty test-pool route, not a provider fix."""
import json, sys
import run as r

stage=sys.argv[1]
pool='10.250.200.0/28'
gw=r.get('eipgateways',r.GW)
assert gw['metadata']['labels']['runbook.ani.io/run']==r.RUN
eip=r.get('eips',r.EIP,r.NS)
assert eip['spec']['subnet']=='kcn-system/'+r.PUBLIC
assert eip['spec']['ipAddress']=='10.250.200.2'
node=eip['status']['boundResource']['nodeName']
er='er.'+node
route=r.ovn(['--format=json','--columns=_uuid,ip_prefix,nexthop,policy','find','Logical_Router_Static_Route','ip_prefix='+pool])
table=json.loads(route['stdout'])
assert len(table['data'])==1,table
row=dict(zip(table['headings'],table['data'][0]))
assert row['nexthop']=='' and row['policy'] in ('src-ip',['set',['src-ip']]),row
uuid=row['_uuid'][1]
owned=r.ovn(['get','Logical_Router',er,'static_routes'])
assert uuid in owned['stdout']
next_hop=gw['status']['localIP']
assert next_hop=='100.64.0.8'
r.save(stage+'-route-override-before.json',{'er':er,'route':row,'gatewayIP':next_hop})
r.ovn(['wait-until','Logical_Router_Static_Route',uuid,'nexthop=""','--','set','Logical_Router_Static_Route',uuid,'nexthop='+next_hop])
after=r.ovn(['get','Logical_Router_Static_Route',uuid,'nexthop'])
r.save(stage+'-route-override-after.json',after)
assert next_hop in after['stdout']
print('TEST-ONLY override',er,pool,'empty ->',next_hop,flush=True)
