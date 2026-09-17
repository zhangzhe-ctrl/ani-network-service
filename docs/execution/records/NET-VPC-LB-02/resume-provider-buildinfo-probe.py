import hashlib,json,os,pathlib,struct,subprocess,sys
name=sys.argv[1]; cli=['/usr/local/bin/crictl','--runtime-endpoint','unix:///run/containerd/containerd.sock']
r=subprocess.run(cli+['ps','-o','json'],capture_output=True,text=True,check=True,timeout=15); candidates=[c for c in json.loads(r.stdout)['containers'] if c['metadata']['name']==name]; out=[]
for c in candidates:
 r=subprocess.run(cli+['inspect',c['id']],capture_output=True,text=True,check=True,timeout=15); inspect=json.loads(r.stdout); pid=int(inspect['info']['pid']); path='/proc/'+str(pid)+'/exe'
 item={'container_id':c['id'],'container_name':name,'pid':pid,'executable':os.readlink(path),'image':c.get('image'),'image_ref':c.get('imageRef')}
 try:
  with open(path,'rb') as f:
   hdr=f.read(64); assert hdr[:6]==b'\x7fELF\x02\x01','requires little-endian ELF64'
   off=struct.unpack_from('<Q',hdr,40)[0]; entsize,num,stringindex=struct.unpack_from('<HHH',hdr,58); assert entsize==64 and num<2000
   f.seek(off); sections=[struct.unpack('<IIQQQQIIQQ',f.read(64)) for _ in range(num)]
   names=sections[stringindex]; assert names[5]<1048576; f.seek(names[4]); strings=f.read(names[5])
   section=next(s for s in sections if strings[s[0]:].split(b'\0',1)[0]==b'.go.buildinfo'); assert section[5]<1048576
   f.seek(section[4]); data=f.read(section[5]); assert data[:14]==b'\xff Go buildinf:' and data[15]&2
   def string_at(pos):
    value=0; shift=0
    while True:
     b=data[pos]; pos+=1; value|=(b&127)<<shift
     if b<128: break
     shift+=7; assert shift<=63
    assert pos+value<=len(data); return data[pos:pos+value],pos+value
   version,pos=string_at(32); mod,pos=string_at(pos)
   if len(mod)>=33 and mod[-17]==10: mod=mod[16:-16]
   lines=mod.decode('utf-8','replace').splitlines(); allowed=[]
   for line in lines:
    if line.startswith(('path\t','mod\t')): allowed.append(line)
    elif line.startswith('build\t') and any(line[6:].startswith(k+'=') for k in ['vcs','vcs.revision','vcs.time','vcs.modified','GOOS','GOARCH','CGO_ENABLED']): allowed.append(line)
   item.update(go_version=version.decode(),build_info_fields=allowed,build_info_sha256=hashlib.sha256(data).hexdigest())
 except Exception as e: item['build_info_error']=type(e).__name__+': '+str(e)
 out.append(item)
print(json.dumps(out))
