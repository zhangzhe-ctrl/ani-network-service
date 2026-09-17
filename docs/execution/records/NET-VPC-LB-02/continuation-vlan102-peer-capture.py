import json,pathlib,socket,struct,time
iface='ens35'; source=bytes.fromhex('000c29e2f02b'); s=socket.socket(socket.AF_PACKET,socket.SOCK_RAW,socket.htons(3));s.bind((iface,0));s.settimeout(.25);s.setsockopt(263,8,1)
def stats(): return {k:int(pathlib.Path('/sys/class/net/'+iface+'/statistics/'+k).read_text()) for k in ['rx_packets','rx_dropped','rx_errors','tx_packets','tx_dropped','tx_errors']}
initial=stats();records=[];count=0;until=time.monotonic()+7;print('READY',flush=True)
while time.monotonic()<until:
 try: data,anc,flags,addr=s.recvmsg(2048,128)
 except socket.timeout: continue
 count+=1
 if len(data)<42 or data[6:12]!=source: continue
 typ=struct.unpack('!H',data[12:14])[0];pos=14;vlan=None
 if typ==0x8100 and len(data)>=46: vlan=struct.unpack('!H',data[14:16])[0]&4095;typ=struct.unpack('!H',data[16:18])[0];pos=18
 for level,ctype,aux in anc:
  if level==263 and ctype==8 and len(aux)>=20:
   status,length,snaplen,macoff,netoff,tci,tpid=struct.unpack('=IIIHHHH',aux[:20])
   if status&16:vlan=tci&4095
 if typ==0x0806 and len(data)>=pos+28:
  a=data[pos:pos+28];records.append({'vlan':vlan,'operation':struct.unpack('!H',a[6:8])[0],'sender':socket.inet_ntoa(a[14:18]),'target':socket.inet_ntoa(a[24:28]),'packet_type':addr[2]})
s.close(); final=stats();print(json.dumps({'interface':iface,'captured_packets':count,'matching_node1_arp':records,'nic_counter_delta':{k:final[k]-initial[k] for k in initial}}))
