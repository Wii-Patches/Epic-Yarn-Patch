import os
import sys, struct
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dol import Dol
from match import textwords
d=Dol(sys.argv[1]); tgt=int(sys.argv[2],16)
a,t=textwords(d)
for i,w in enumerate(t):
    if w>>26==18 and w&1:
        off=w&0x03FFFFFC
        if off&0x02000000: off-=0x04000000
        if (a+i*4+off)==tgt: print(hex(a+i*4))
