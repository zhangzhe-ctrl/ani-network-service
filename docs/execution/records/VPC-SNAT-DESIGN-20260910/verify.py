"""Local, read-only checks of document inputs; writes only its verification result."""
import datetime, hashlib, json, pathlib, re, subprocess, urllib.parse
import yaml

HERE=pathlib.Path(__file__).resolve().parent
ROOT=HERE.parents[3]
KC=pathlib.Path('/home/chabking/workspace/kc-networking')
RECORD=ROOT/'docs/execution/records/KC-OVERLAY-20260910T114200Z'
DOCS=[ROOT/p for p in ['CONTEXT.md','docs/START-HERE.md','docs/execution/status.md','docs/specs/vpc-subnet.md','docs/specs/vpc-snat.md','docs/plans/vpc-snat.md','docs/kc-public-egress-manual.md','docs/execution/records/2026-09-10-vpc-snat-design.md']]
SHA='a2245883eb2b46a998f041feb3ad0ed3f6cf7c60'
assert subprocess.check_output(['git','-C',str(KC),'rev-parse','HEAD'],text=True).strip()==SHA

def anchors(path):
    result=set(); duplicates={}
    in_fence=False
    for line in path.read_text().splitlines():
        if line.startswith('```'): in_fence=not in_fence
        if in_fence: continue
        m=re.match(r'^#{1,6} (.*)',line)
        if not m: continue
        value=m[1].replace('`','').lower().strip()
        value=re.sub(r'[^\w\-\s]','',value).replace(' ','-')
        n=duplicates.get(value,0);duplicates[value]=n+1
        result.add(value if n==0 else value+'-'+str(n))
    return result

links=0;fragment_checks=0
for doc in DOCS:
    body=doc.read_text()
    assert body.count('```')%2==0,doc
    for link in re.findall(r'\]\(([^)\n]+)\)',body):
        if '://' in link: continue
        path,_,fragment=link.partition('#')
        target=(doc.parent/urllib.parse.unquote(path)).resolve() if path else doc
        assert target.exists(),(doc,link)
        if fragment:
            assert urllib.parse.unquote(fragment) in anchors(target),(doc,link)
            fragment_checks+=1
        links+=1

manual=(ROOT/'docs/kc-public-egress-manual.md').read_text()
blocks=re.findall(r'```bash\n(.*?)\n```',manual,re.S)
for i,block in enumerate(blocks):
    p=subprocess.run(['bash','-n'],input=block,text=True,capture_output=True)
    assert p.returncode==0,(i,p.stderr)

values={'KC_DEV':'ens224','KC_VLAN':'public-uplink','KC_VLAN_ID':'0','KC_EIP_GW':'public-egress','KC_SYSTEM_NS':'kcn-system',
'UL_PUBLIC_CIDR':'198.51.100.0/24','UL_OVN_GATEWAY_IP':'198.51.100.1','UL_SWITCH_GATEWAY_IP':'198.51.100.254','UL_RESERVED_RANGE':'198.51.100.1..198.51.100.20',
'OL_PUBLIC_CIDR':'203.0.113.0/24','OL_OVN_GATEWAY_IP':'203.0.113.1','OL_RESERVED_RANGE':'203.0.113.1..203.0.113.20',
'TENANT_NS':'tenant-00000000-0000-4000-8000-000000000001','VPC_NAME':'vpc-egress-manual','PRIVATE_VPC_CIDR':'10.240.0.0/16',
'PRIVATE_SUBNET':'subnet-egress-manual','PRIVATE_SUBNET_CIDR':'10.240.1.0/24','PRIVATE_GATEWAY_IP':'10.240.1.1','EIP_NAME':'eip-example-overlay-01','PUBLIC_POOL':'public-overlay',
'PROBE_NAME':'egress-probe','EGRESS_PROBE_IMAGE':'example.invalid/probe:v1','TEST_DNS_IP':'1.1.1.1','SNAT_NAME':'snat-example-overlay-01'}
crds={}
for path in (KC/'config/crd/bases').glob('*.yaml'):
    obj=yaml.safe_load(path.read_text())
    if not isinstance(obj,dict) or obj.get('kind')!='CustomResourceDefinition':continue
    crds[obj['spec']['names']['kind']]=obj

def structure(value,schema,where):
    kind=schema.get('type')
    if kind=='object':
        assert isinstance(value,dict),where
        for name in schema.get('required',[]):assert name in value,(where,'missing',name)
        props=schema.get('properties',{})
        for name,item in value.items():
            if name in props: structure(item,props[name],where+'.'+name)
            elif isinstance(schema.get('additionalProperties'),dict):structure(item,schema['additionalProperties'],where+'.'+name)
            else:assert not props,(where,'unknown field',name)
    elif kind=='array':
        assert isinstance(value,list),where
        for item in value:structure(item,schema['items'],where+'[]')
    elif kind=='string':assert isinstance(value,str),where
    elif kind=='integer':assert isinstance(value,int) and not isinstance(value,bool),where
    elif kind=='boolean':assert isinstance(value,bool),where
    if 'enum' in schema:assert value in schema['enum'],(where,value)
    if 'minimum' in schema:assert value>=schema['minimum'],where
    if 'maximum' in schema:assert value<=schema['maximum'],where

objects={};checked_specs=0
for name,body in re.findall(r'cat > ([^\n]+?) <<EOF\n(.*?)\nEOF',manual,re.S):
    body=re.sub(r'\$\{([A-Z_0-9]+)\}',lambda m: values[m[1]],body)
    assert '${' not in body,name
    obj=yaml.safe_load(body);objects[name]=obj
    if obj['apiVersion']=='networking.kubercloud.com/v1':
        crd=crds[obj['kind']]
        schema=next(v for v in crd['spec']['versions'] if v['name']=='v1')['schema']['openAPIV3Schema']['properties']['spec']
        structure(obj['spec'],schema,name+'.spec');checked_specs+=1
        if crd['spec']['scope']=='Cluster':assert 'namespace' not in obj['metadata'],name
        else: assert obj['metadata']['namespace']==('kcn-system' if obj['spec'].get('type')=='Public' else values['TENANT_NS']),name
assert len(objects)==9 and checked_specs==8
assert 'underlayConfig' not in objects['public-overlay.yaml']['spec']
assert objects['public-underlay.yaml']['spec']['underlayConfig']['vlanNetwork']=='public-uplink'
for name in ['public-overlay.yaml','public-underlay.yaml']:
    assert objects[name]['spec']['allowedNamespaces']['from']=='All'
assert objects['tenant-snat.yaml']['spec']=={'eip':values['EIP_NAME'],'vpc':values['VPC_NAME'],'disable':False}

source_links=0
for sha,path in re.findall(r'https://gitlab\.changqingyun\.cn/kubercloud/sdn/kc-networking/-/blob/([a-f0-9]+)/([^\s)]+)',manual):
    assert sha==SHA and (KC/path).is_file(),(sha,path)
    source_links+=1

preserved=0
for line in (RECORD/'SHA256SUMS').read_text().splitlines():
    digest,name=line.split('  ',1)
    assert hashlib.sha256((RECORD/name).read_bytes()).hexdigest()==digest,name
    preserved+=1
audit=json.loads((RECORD/'audit-result.json').read_text())
assert audit['native_overlay_egress']=='fail' and audit['counterfactual_route_override_egress']=='pass'
assert audit['exact_ovn_baseline_restored'] is False
assert 'fail' in audit['dns_dependent_request']
subprocess.run(['git','-C',str(ROOT),'diff','--check'],check=True)

result={'at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'execution_host':'local workstation','result':'pass','documents_checked':len(DOCS),'relative_links':links,'anchors_checked':fragment_checks,'bash_blocks_syntax_checked':len(blocks),'yaml_templates_parsed':len(objects),'kc_cr_specs_structurally_checked':checked_specs,'fixed_kc_source_links':source_links,'historical_evidence_files_sha256_verified':preserved,'historical_overlay_native_result':audit['native_overlay_egress'],'historical_overlay_counterfactual_result':audit['counterfactual_route_override_egress'],'historical_full_ovn_restore':False,'git_diff_check':'pass','kubernetes_admission_cel_ipam':'not_verified: offline structure only','new_live_testing':'not_run','make_verify':'not_run: documentation only, no commit','external_website_access':'not_verified: source links matched to local fixed SHA','full_json_schema_validation':'not_run: jsonschema unavailable'}
(HERE/'verification.json').write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n')
print(json.dumps(result,indent=2,ensure_ascii=False))
