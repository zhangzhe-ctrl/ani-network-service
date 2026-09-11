import copy, json
import run as r

events=r.run(r.K+['get','events','-n',r.NS,'--field-selector','type=Warning','-o','json'])
r.save('probe-image-first-attempt-events.json',json.loads(events['stdout']))
obj=json.loads((r.ROOT/'manifest-pod-probe-10.json').read_text())
r.save('attempt-pod-probe-10-unresolvable-digest.json',obj)
obj['spec']['containers'][0]['image']=r.IMAGE
r.save('manifest-pod-probe-10.json',obj)
r.run(r.K+['patch','pod','probe-10','-n',r.NS,'--type=strategic','-p',json.dumps({'spec':{'containers':[{'name':'probe','image':r.IMAGE}]}})])
r.wait('pod','probe-10',r.NS)
other=copy.deepcopy(obj)
other['metadata']['name']='probe-11'
other['metadata']['annotations']['networking.kubercloud.com/subnet']=r.NS+'/'+r.RUN+'-subnet-11'
other['spec']['nodeName']='kc062-worker2'
other['spec']['containers'][0]['env'][1]['value']=r.RUN+'-probe-11'
r.create(other)
r.wait('pod','probe-11',r.NS)
for i in [10,11]:
    obj=r.get('pod','probe-'+str(i),r.NS)
    image=obj['status']['containerStatuses'][0]['imageID']
    assert image.endswith('8b305a958323064c72a1215a35b41cb5af96f1c435d33e5425664572a2b85176'),image
    assert obj['status']['podIP'].startswith(f'10.241.{i}.')
    print('ready',obj['metadata']['name'],obj['status']['podIP'],image,flush=True)
    r.run(r.K+['exec','-n',r.NS,'probe-'+str(i),'--','/probe','inspect'])
