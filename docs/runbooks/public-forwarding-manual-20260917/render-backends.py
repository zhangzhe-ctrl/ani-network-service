#!/usr/bin/env python3
"""Read two ready Pods and emit Backend JSON. Does not create resources."""
import ipaddress,json,subprocess
ns='pubdebug-20260917';items=[]
for name in ['backend-a','backend-b']:
 pod=json.loads(subprocess.check_output(['sudo','kubectl','--request-timeout=15s','-n',ns,'get','pod',name,'-o','json']))
 assert any(c['type']=='Ready' and c['status']=='True' for c in pod['status'].get('conditions',[])),name+' not Ready'
 ip=str(ipaddress.IPv4Address(pod['status']['podIP']))
 assert ipaddress.ip_address(ip) in ipaddress.ip_network('10.233.1.0/24')
 items.append({'apiVersion':'gateway.envoyproxy.io/v1alpha1','kind':'Backend','metadata':{'namespace':ns,'name':name,'labels':{'manual.ani.io/run':ns}},'spec':{'type':'Endpoints','endpoints':[{'ip':{'address':ip,'port':8080}}]}})
print(json.dumps({'apiVersion':'v1','kind':'List','items':items},indent=2))
