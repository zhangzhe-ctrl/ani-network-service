import pathlib,json,sys,datetime
r=pathlib.Path('/home/chabking/workspace/ani-resource-service-runs/rsmod-20260921T1640Z/control-20260922T0400Z');p=r/'private/runtime/checkpoints';a,b=sys.argv[1:3]
x=json.loads((p/a/'identities.json').read_text());y=json.loads((p/b/'identities.json').read_text());diff=[{'object':k,'expected':v,'actual':y.get(k)} for k,v in x.items() if y.get(k)!=v]
res={'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'from':a,'to':b,'compared':len(x),'extra_objects':sorted(set(y)-set(x)),'differences':diff,'result':'pass' if not diff else 'fail','fields':['UID','labels','ownerReferences','spec','fieldManagers'],'status_resourceVersion':'excluded as mutable observations'}
(r/'evidence'/f'compare-{a}-{b}.json').write_text(json.dumps(res,indent=2)+'\n');print(json.dumps({k:v for k,v in res.items() if k!='differences'}));sys.exit(bool(diff))
