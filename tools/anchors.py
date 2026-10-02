"""Find the Kirby's Epic Yarn addresses the GameCube-pad patch needs in any region.

Everything is written once against the USA disc (RK5E01); the other discs share
the same compiled code at other addresses.  A function is located by matching
a window of USA instructions against the target DOL with the relocatable bits
(branch displacements, address halves, small-data offsets) masked out, and it
must match exactly once.  Data addresses are then read back from the matched
code (the lis/addi that references them), never guessed.
"""
import os, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dol import Dol


def mask(w):
    op = w >> 26
    if op == 18:                         # b / bl: keep opcode, AA, LK
        return w & 0xFC000003
    if op == 16:                         # bc: keep everything but displacement
        return w & 0xFFFF0003
    if op in (14, 15, 24, 25, 26, 27, 28, 29):   # addi/lis/ori/oris/xori/andi
        return w & 0xFFFF0000
    if 32 <= op <= 55:                   # loads/stores: drop displacement
        return w & 0xFFFF0000
    return w


def words(d, va, n):
    b = d.read(va, n * 4)
    return list(struct.unpack('>%dI' % n, b)) if b and len(b) == n * 4 else None


def simm(w):
    v = w & 0xFFFF
    return v - 0x10000 if v & 0x8000 else v


class Finder:
    def __init__(self, ref, tgt):
        self.ref, self.tgt = ref, tgt
        o, a, s, _ = [x for x in tgt.secs if x[3] == 1][0]
        self.tw = struct.unpack('>%dI' % (s // 4), tgt.data[o:o + s])
        self.tbase = a
        self.tm = [mask(w) for w in self.tw]

    def locate(self, ref_va, n=24):
        """address in the target of the code at ref_va; must match exactly once"""
        rw = words(self.ref, ref_va, n)
        rm = [mask(w) for w in rw]
        hits, first = [], rm[0]
        for i in range(len(self.tm) - n):
            if self.tm[i] == first and self.tm[i:i + n] == rm:
                hits.append(self.tbase + i * 4)
        if len(hits) != 1:
            raise SystemExit('anchor %08X: %d matches' % (ref_va, len(hits)))
        return hits[0]

    def pair(self, ref_va, ref_target, n=64):
        """the target's value for the address that the lis + addi pair near ref_va
        loads (ref_target in the reference)"""
        t_va = self.locate(ref_va)
        rw = words(self.ref, ref_va, n)
        tw = words(self.tgt, t_va, n)
        for i in range(n):
            w = rw[i]
            if w >> 26 != 15:
                continue
            reg = (w >> 21) & 31
            for j in range(i + 1, min(n, i + 16)):
                w2 = rw[j]
                if w2 >> 26 == 14 and (w2 >> 16) & 31 == reg:
                    val = ((w & 0xFFFF) << 16) + simm(w2)
                    if val & 0xFFFFFFFF == ref_target:
                        t, t2 = tw[i], tw[j]
                        assert t >> 26 == 15 and t2 >> 26 == 14
                        return (((t & 0xFFFF) << 16) + simm(t2)) & 0xFFFFFFFF
        raise SystemExit('no pair for %08X near %08X' % (ref_target, ref_va))


def sda_base(d):
    """r13 as the start code loads it (lis/ori pair in the first text section)"""
    o, a, s, _ = [x for x in d.secs if x[3] == 0][0]
    t = struct.unpack('>%dI' % (s // 4), d.data[o:o + s])
    for i in range(len(t) - 1):
        if t[i] >> 26 == 15 and (t[i] >> 21) & 31 == 13 and t[i + 1] >> 26 == 24 and (t[i + 1] >> 21) & 31 == 13:
            return ((t[i] & 0xFFFF) << 16) | (t[i + 1] & 0xFFFF)
    raise SystemExit('no r13 setup found')


# (name, USA address, window)
FUNCS = {
    'KPADiRead': (0x806FABF0, 40),
    'WPADProbe': (0x806B56F0, 30),
    'SIGetType': (0x8069FCF0, 40),
    'OSDisableInterrupts': (0x80668180, 5),
    'OSRestoreInterrupts': (0x806681C0, 4),
}
# offsets inside KPADiRead (identical code in every region)
SAMPLE_OFF = 0x806FAD94 - 0x806FABF0         # lbz r0,0x17b(r21)
POST_OFF = 0x806FB35C - 0x806FABF0           # cmpwi r29,0  (every path out of the function)
# the game's pad poller; its 'addi r26,r13,-0x16e4' is the per-channel "sideways" flag array
PAD_POLL = 0x8063B958
PAD_POLL_FLAG_OFF = 0x8063B9AC - PAD_POLL


def resolve(ref, tgt):
    f = Finder(ref, tgt)
    r = {}
    for k, (va, n) in FUNCS.items():
        r[k] = f.locate(va, n)
    r['Sample'] = r['KPADiRead'] + SAMPLE_OFF
    r['Post'] = r['KPADiRead'] + POST_OFF
    r['SiTypes'] = f.pair(0x8069FCF0, 0x808CDB58)
    r['SiBusy'] = r['SiTypes'] - 0x18
    r['SiShadow'] = r['SiBusy'] + 4
    r['WpadTbl'] = f.pair(0x806B56F0, 0x80928ED0)
    r['GamePad'] = f.pair(PAD_POLL, 0x808FC4C0)           # the game's own per-channel KPADStatus array (tests only)
    poll = f.locate(PAD_POLL, 24)
    w = words(tgt, poll + PAD_POLL_FLAG_OFF, 1)[0]
    assert w >> 26 == 14 and (w >> 16) & 31 == 13, 'sideways flag instruction not where expected'
    r['Sideways'] = (sda_base(tgt) + simm(w)) & 0xFFFFFFFF
    return r


if __name__ == '__main__':
    ref = Dol(sys.argv[1])
    for p in sys.argv[2:]:
        r = resolve(ref, Dol(p))
        print(os.path.basename(p), {k: '%08X' % v for k, v in r.items()})
