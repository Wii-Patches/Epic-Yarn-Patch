import os
import sys, struct
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from dol import Dol
d=Dol(sys.argv[1]); tgt=int(sys.argv[2],16)
hi=((tgt+0x8000)>>16)&0xFFFF; lo=tgt&0xFFFF
o,a,s,_=[x for x in d.secs if x[3]==1][0]
t=struct.unpack('>%dI'%(s//4),d.data[o:o+s])
for i,w in enumerate(t):
    if w>>26==15 and (w&0xFFFF)==hi:
        reg=(w>>21)&31
        for j in range(i+1,min(i+12,len(t))):
            w2=t[j]
            if w2>>26 in(14,24,32,33,34,35,36,37,38,39,48,50,52,54) and ((w2>>16)&31)==reg and (w2&0xFFFF)==lo:
                print(hex(a+i*4),hex(a+j*4))
