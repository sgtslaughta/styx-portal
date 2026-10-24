import sys,re
ev=[(l.split()[1],float(l.split()[2])) for l in open(sys.argv[1]) if l.startswith("SPIKE")]
c=[t for e,t in ev if e=="refit-close"]
if not c: print("no refit"); sys.exit()
c=c[0]; after=[(e,round((t-c)*1000)) for e,t in ev if t>=c]
up=next((ms for e,ms in after if e=="ws-upgrade"),None); ff=next((ms for e,ms in after if e=="first-frame"),None)
print(f"{sys.argv[2]:12s} reconnect-arrives=+{up}ms first-video-frame=+{ff}ms")
