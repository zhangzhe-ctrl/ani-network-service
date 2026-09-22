import sys,pathlib
r=pathlib.Path('/home/chabking/workspace/ani-resource-service-runs/rsmod-20260921T1640Z/control-20260922T0400Z')
s=r.parent/'records-closeout-20260922T0225Z/source/docs/execution/records/NET-VPC-LB-02/health-port-live-20260917'
component=sys.argv.pop(1);name={'runtime':'live-runtime.py','platform':'live-platform-driver.py','product':'live-product-driver.py'}[component];text=(s/name).read_text()
if component=='runtime':
 a="if directory != Path('/home/chabking/workspace/ani-network-service-runs/lb-health-e2e-20260917/private/runtime') or plan[\"run\"] != 'lbhealth-0917':"
 b=f"if directory != Path({str(r/'private/runtime')!r}) or plan[\"run\"] != 'rsctl-0922':"
 assert text.count(a)==1;text=text.replace(a,b)
else:
 assert text.count('NET-VPC-LB-02-HEALTH')=={'platform':4,'product':2}[component]
 text=text.replace('NET-VPC-LB-02-HEALTH','RESOURCE-MOD-20260922')
exec(compile(text,str(s/name),'exec'),{'__name__':'__main__','__file__':str(s/name)})
