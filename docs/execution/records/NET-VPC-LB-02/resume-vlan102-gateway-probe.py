import datetime,json,pathlib,socket,struct,time
iface='ens35'; vlan=102; target='172.16.102.1'; mac=bytes.fromhex(pathlib.Path('/sys/class/net/'+iface+'/address').read_text().strip().replace(':',''))
s=socket.socket(socket.AF_PACKET,socket.SOCK_RAW,socket.htons(3)); s.bind((iface,0)); s.settimeout(0.25)
s.setsockopt(263,8,1)
arp=struct.pack('!HHBBH',1,0x0800,6,4,1)+mac+socket.inet_aton('0.0.0.0')+bytes(6)+socket.inet_aton(target)
frame=(bytes.fromhex('ffffffffffff')+mac+struct.pack('!HHH',0x8100,vlan,0x0806)+arp).ljust(60,b'\x00')
replies=[]; sent=0
for attempt in range(2):
 s.send(frame); sent+=1; until=time.monotonic()+1.2
 while time.monotonic()<until:
  try: packet,anc,flags,addr=s.recvmsg(4096,128)
  except socket.timeout: continue
  if len(packet)<42: continue
  typ=struct.unpack('!H',packet[12:14])[0]; offset=14; tag=None
  if typ==0x8100 and len(packet)>=46: tag=struct.unpack('!H',packet[14:16])[0]&4095; typ=struct.unpack('!H',packet[16:18])[0]; offset=18
  for level,ctype,data in anc:
   if level==263 and ctype==8 and len(data)>=20:
    status,length,snaplen,macoff,netoff,tci,tpid=struct.unpack('=IIIHHHH',data[:20])
    if status&16: tag=tci&4095
  if typ!=0x0806 or len(packet)<offset+28: continue
  payload=packet[offset:offset+28]; op=struct.unpack('!H',payload[6:8])[0]; sender=socket.inet_ntoa(payload[14:18])
  if op==2 and sender==target and payload[18:24]==mac:
   item={'sender_ip':sender,'sender_mac':':'.join(format(x,'02x') for x in payload[8:14]),'vlan_from_frame_or_auxdata':tag,'target_mac_matches_interface':True}
   if item not in replies: replies.append(item)
s.close(); print(json.dumps({'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'interface':iface,'transmit_vlan':vlan,'target':target,'sender_ip':'0.0.0.0','frames_sent':sent,'replies':replies,'host_configuration_changes':0,'result':'pass' if any(x['vlan_from_frame_or_auxdata']==vlan for x in replies) else 'not_verified'}))
