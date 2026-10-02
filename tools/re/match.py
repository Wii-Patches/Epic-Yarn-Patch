import os
import sys, struct
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dol import Dol
def mask(w):
    op=w>>26
    if op==18: return w&0xFC000003
    if op==16: return w&0xFFFF0003
    if op in (14,15,24,25,26,27,28,29): return w&0xFFFF0000
    if 32<=op<=55: return w&0xFFFF0000
    return w
def textwords(d):
    o,a,s,_=[x for x in d.secs if x[3]==1][0]
    return a, struct.unpack('>%dI'%(s//4), d.data[o:o+s])
if __name__=='__main__':
    ref=Dol(sys.argv[1]); tgt=Dol(sys.argv[2]); ra=int(sys.argv[3],16); n=int(sys.argv[4])
    rw=struct.unpack('>%dI'%n, ref.read(ra,n*4)); rm=[mask(w) for w in rw]
    a,t=textwords(tgt); tm=[mask(w) for w in t]
    hits=[a+i*4 for i in range(len(tm)-n) if tm[i]==rm[0] and tm[i:i+n]==rm]
    print([hex(h) for h in hits])
