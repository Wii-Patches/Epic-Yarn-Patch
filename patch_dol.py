#!/usr/bin/env python3
"""Apply the GameCube-controller patch to a Kirby's Epic Yarn main.dol.

  patch_dol.py <region id> <in main.dol> <out main.dol>      (RK5E01 RK5P01 RK5J01 RK5K01)

The code goes in a new DOL text section at 0x80001820 (below the OS globals at
0x80003000, clear of everything the game uses, and not 0x80001800, which a
loader's code handler overwrites).  Each hook site becomes a branch into its
stub; the stub runs the instruction it replaced and branches back, which is
what a Gecko C2 does.  `patches.json` is written by gcbuild.py and holds only
this project's code, never anything from the game.
"""
import json, os, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))
LIMIT = 0x80003000


class PatchError(RuntimeError):
    pass


def branch(frm, to):
    off = to - frm
    assert off % 4 == 0 and -0x2000000 <= off < 0x2000000
    return 0x48000000 | (off & 0x03FFFFFC)


class Dol:
    def __init__(self, data):
        self.d = bytearray(data)
        self.off = list(struct.unpack('>18I', self.d[0x00:0x48]))
        self.addr = list(struct.unpack('>18I', self.d[0x48:0x90]))
        self.size = list(struct.unpack('>18I', self.d[0x90:0xD8]))

    def v2f(self, va):
        for o, a, s in zip(self.off, self.addr, self.size):
            if s and a <= va < a + s:
                return o + va - a
        return None

    def word(self, va):
        fo = self.v2f(va)
        if fo is None:
            raise PatchError('address 0x%08X is not in the DOL' % va)
        return struct.unpack('>I', self.d[fo:fo + 4])[0]

    def put(self, va, word):
        fo = self.v2f(va)
        self.d[fo:fo + 4] = struct.pack('>I', word)

    def add_text(self, va, blob):
        slot = next((i for i in range(7) if self.size[i] == 0), None)
        if slot is None:
            raise PatchError('no free text section in the DOL header')
        for a, s in zip(self.addr, self.size):
            if s and a < va + len(blob) and va < a + s:
                raise PatchError('0x%08X overlaps an existing section' % va)
        while len(self.d) % 0x20:
            self.d.append(0)
        self.off[slot], self.addr[slot], self.size[slot] = len(self.d), va, len(blob)
        self.d += blob
        self.d[0x00:0x48] = struct.pack('>18I', *self.off)
        self.d[0x48:0x90] = struct.pack('>18I', *self.addr)
        self.d[0x90:0xD8] = struct.pack('>18I', *self.size)


def state(data, patch):
    """'unpatched' (every hook site holds the original instruction), 'patched', or 'mismatch'"""
    dol = Dol(data)
    base, end = patch['base'], patch['base'] + len(patch['blob']) // 2
    try:
        words = [dol.word(s['site']) for s in patch['sites']]
    except PatchError:
        return 'mismatch'
    if all(w == s['orig'] for w, s in zip(words, patch['sites'])):
        return 'unpatched'
    if all(w == branch(s['site'], s['hook']) for w, s in zip(words, patch['sites'])) \
            and any(a == base for a in dol.addr):
        return 'patched'
    return 'mismatch'


def apply(data, patch):
    """patch: one region of patches.json"""
    st = state(data, patch)
    if st == 'patched':
        raise PatchError('this disc already has GameCube controller support')
    if st != 'unpatched':
        raise PatchError('main.dol does not match the expected build of the game '
                         '(an unexpected version, or patched with something else)')
    blob = bytes.fromhex(patch['blob'])
    if patch['base'] + len(blob) > LIMIT:
        raise PatchError('patch does not fit below 0x%08X' % LIMIT)
    dol = Dol(data)
    dol.add_text(patch['base'], blob)
    for s in patch['sites']:
        dol.put(s['site'], branch(s['site'], s['hook']))
    return bytes(dol.d)


def load(region, name='patches.json', root=HERE):
    return json.load(open(os.path.join(root, name)))[region]


if __name__ == '__main__':
    region, src, dst = sys.argv[1:4]
    out = apply(open(src, 'rb').read(), load(region, os.environ.get('PATCHES', 'patches.json')))
    open(dst, 'wb').write(out)
    print('%s: patched (%d bytes added)' % (region, len(out) - os.path.getsize(src)))
