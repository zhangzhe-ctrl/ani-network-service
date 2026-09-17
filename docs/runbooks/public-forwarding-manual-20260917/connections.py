#!/usr/bin/env python3
"""Read actual TCP peers inside public-b. Only kubectl exec cat; no network probe."""
import ipaddress,json,subprocess,datetime
ns='pubdebug-20260917'
def addr(word):
 h,p=word.split(':');b=bytes.fromhex(h)
 b=b[::-1] if len(b)==4 else b''.join(b[i:i+4][::-1] for i in range(0,16,4))
 a=ipaddress.ip_address(b)
 if isinstance(a,ipaddress.IPv6Address) and a.ipv4_mapped:a=a.ipv4_mapped
 return str(a),int(p,16)
items=[]
for path in ['/proc/net/tcp','/proc/net/tcp6']:
 data=subprocess.check_output(['sudo','kubectl','--request-timeout=15s','-n',ns,'exec','public-b','-c','probe','--','cat',path],text=True)
 for line in data.splitlines()[1:]:
  f=line.split();local,port=addr(f[1]);peer,peer_port=addr(f[2])
  if port==8080 and f[3]=='01':items.append({'local':local,'local_port':port,'peer':peer,'peer_port':peer_port,'state':'ESTABLISHED','expected_snat_source':peer=='172.16.102.196'})
print(json.dumps({'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'receiver':'public-b','connections':items},indent=2))
