import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from dol import Dol
from capstone import *
d=Dol(sys.argv[1]); a=int(sys.argv[2],16); n=int(sys.argv[3],0)
md=Cs(CS_ARCH_PPC, CS_MODE_32|CS_MODE_BIG_ENDIAN); md.skipdata=True
b=d.read(a,n*4)
for i in md.disasm(b,a):
    print('%08x  %s %s'%(i.address,i.mnemonic,i.op_str))
