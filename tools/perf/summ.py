import sys,re,statistics as st,csv
f=sys.argv[1]
rows=[r for r in csv.reader(open(f)) if len(r)>=4 and r[2].isdigit() and r[3].isdigit() and int(r[3])>0]
for lab in sorted({r[0] for r in rows}):
  for m in ['verify','speed']:
    t=[int(r[3]) for r in rows if r[0]==lab and r[1]==m]; fb=[int(r[5]) for r in rows if r[0]==lab and r[1]==m]
    if t: print(lab, m, len(t), 'median', st.median(t), 'range', min(t), max(t), 'fallbacks', st.median(fb))
agg={}
for line in open(f):
    m=re.match(r'([\w.-]+),(\w+),frames=(\d+),janky=(\d+) \(([\d.]+)%\),p50=(\d+)ms,p90=(\d+)ms,p95=(\d+)ms,p99=(\d+)ms',line)
    if m: agg.setdefault((m[1],m[2]),[]).append([float(x) for x in m.groups()[2:]])
for k,v in sorted(agg.items()):
    a=[sum(c)/len(c) for c in zip(*v)]
    print(k,'frames=%d janky%%=%.1f p50=%.0f p90=%.0f p95=%.0f p99=%.0f'%(a[0],a[2],a[3],a[4],a[5],a[6]))
