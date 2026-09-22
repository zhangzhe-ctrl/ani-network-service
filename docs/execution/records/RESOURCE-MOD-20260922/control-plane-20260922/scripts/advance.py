import pathlib,subprocess,time,sys,json,datetime
r=pathlib.Path('/home/chabking/workspace/ani-resource-service-runs/rsmod-20260921T1640Z/control-20260922T0400Z')
label=sys.argv[1];start=time.monotonic();attempt=0
while True:
 attempt+=1
 x=subprocess.run(['python3',str(r/'step.py'),label+f'-wait{attempt}',*sys.argv[2:]],capture_output=True,text=True)
 print(x.stdout,flush=True)
 if x.returncode!=3:sys.exit(x.returncode)
 if time.monotonic()-start>180:sys.exit(3)
 # Exit 3 is the frozen driver's pending async prerequisite, not a failed assertion.
 time.sleep(5)
