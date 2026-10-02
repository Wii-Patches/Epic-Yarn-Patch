#!/usr/bin/env python3
"""Build the GameCube-pad hooks for every Kirby's Epic Yarn region.

  gcbuild.py [--debug-feed]

Resolves the addresses (tools/anchors.py) in each region's main.dol, compiles
src/gcpad.c + src/hooks.S against them with devkitPPC, and writes patches.json:
one blob per region and the four branch sites that jump into it.  patches.json
holds only this project's code, never any game bytes.  The shipped
patches.json is checked in, so only developers need devkitPPC and the DOLs.

--debug-feed builds a test variant (patches_feed.json) whose pad reads come
from gc_state.feed[] instead of the SI hardware, so a debugger can drive it.
"""
import json, os, struct, subprocess, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, 'tools'))
from dol import Dol
import anchors

DEVKIT = os.environ.get('DEVKITPPC', '/opt/devkitpro/devkitPPC')
CC = DEVKIT + '/bin/powerpc-eabi-'
BASE = 0x80001820          # a new DOL text section here: below the OS globals at 0x80003000
REGIONS = {'RK5E01': 'USA', 'RK5P01': 'Europe', 'RK5J01': 'Japan', 'RK5K01': 'Korea'}
HOOKS = [('poll', 'KPADiRead', 'POLL'), ('sample', 'Sample', 'SAMPLE'), ('probe', 'WPADProbe', 'PROBE')]
# Vague Rant and crediar's Classic Controller Support (B/A mode) v1.1, written for the USA disc (vr/RK5E01.txt) and
# moved to the other regions by KPADiRead's offset.  The sites each region's published code uses (checked):
VR_SITES = {'RK5E01': [0x806F8080, 0x806F9350, 0x806F9D00, 0x806F7CDC],
            'RK5P01': [0x806F88E0, 0x806F9BB0, 0x806FA560, 0x806F853C],
            'RK5J01': [0x806F7DE0, 0x806F90B0, 0x806F9A60, 0x806F7A3C],
            'RK5K01': [0x806F9200, 0x806FA4D0, 0x806FAE80, 0x806F8E5C]}
VR_USA_KPADIREAD = 0x806FABF0
VR_ASPECT = 0x806B0A70            # SCGetAspectRatio's neighbour the pointer code calls (lis/ori pair in the code)


def dol_dir():
    return os.environ.get('KEY_DOLS', 'dols')       # a directory of <REGION>.dol


def compile_region(a, debug_feed, yb=False):
    src = os.path.join(HERE, 'src')
    tmp = tempfile.mkdtemp(prefix='gcpad')
    D = {
        'SI_TYPES': a['SiTypes'], 'SI_BUSY': a['SiBusy'], 'SI_SHADOW': a['SiShadow'],
        'FN_SIGETTYPE': a['SIGetType'], 'FN_OSDISABLE': a['OSDisableInterrupts'],
        'FN_OSRESTORE': a['OSRestoreInterrupts'], 'WPAD_TBL': a['WpadTbl'],
    }
    rets = {'POLL_RET': a['KPADiRead'] + 4, 'SAMPLE_RET': a['Sample'] + 4, 'PROBE_RET': a['WPADProbe'] + 4}
    defs = ['-D%s=0x%08Xu' % kv for kv in D.items()] + ['-DHOOK_' + h[2] for h in HOOKS]
    if debug_feed:
        defs.append('-DDEBUG_FEED')
    if yb:
        defs.append('-DLAYOUT_YB')
    cflags = ['-O2', '-fno-unroll-loops', '-mbig-endian', '-msoft-float', '-msdata=none', '-ffreestanding',
              '-fno-pic', '-fno-asynchronous-unwind-tables', '-fno-stack-protector', '-nostdlib', '-Wall',
              '-mno-sdata', '-fno-builtin']
    subprocess.check_call([CC + 'gcc'] + cflags + defs + ['-c', src + '/gcpad.c', '-o', tmp + '/g.o'])
    subprocess.check_call([CC + 'gcc', '-mbig-endian', '-c', '-x', 'assembler-with-cpp'] + defs +
                          [src + '/hooks.S', '-o', tmp + '/h.o'])
    ld = [CC + 'ld', '--defsym', 'BASE=0x%X' % BASE]
    for k, v in rets.items():            # the stubs branch back to these (resolved as relative branches)
        ld += ['--defsym', '%s=0x%X' % (k, v)]
    subprocess.check_call(ld + ['-T', src + '/link.ld', '-o', tmp + '/b.elf', tmp + '/h.o', tmp + '/g.o'])
    subprocess.check_call([CC + 'objcopy', '-O', 'binary', tmp + '/b.elf', tmp + '/b.bin'])
    syms = {}
    for ln in subprocess.check_output([CC + 'nm', tmp + '/b.elf'], text=True).splitlines():
        p = ln.split()
        if len(p) == 3:
            syms[p[2]] = int(p[0], 16)
    blob = open(tmp + '/b.bin', 'rb').read()
    return blob, syms


def parse_vr(path):
    """the Gecko C2 codes of a text file -> [(site, [words])]"""
    L = [l.split() for l in open(path).read().splitlines()[1:] if l.strip()]
    out, i = [], 0
    while i < len(L):
        h = L[i]
        assert h[0].startswith('C2'), h
        n = int(h[1], 16)
        words = [int(x, 16) for l in L[i + 1:i + 1 + n] for x in l]
        out.append((0x80000000 | (int(h[0], 16) & 0x01FFFFFF), words))
        i += 1 + n
    return out


# Y/B mode differs from B/A mode only in four constants of the button injector (the last code): which remote button
# each of A, B, X, Y presses.  CC button mask -> (B/A word, Y/B word)
YB_SWAP = {0x70E50010: (0x60C60100, 0x60C60800), 0x70E50040: (0x60C60200, 0x60C60100),
           0x70E50008: (0x60C60800, 0x60C60400), 0x70E50020: (0x60C60400, 0x60C60200)}


def to_yb(words):
    """B/A -> Y/B: the `andi.` of each face button is followed by `beq +8; ori r6,r6,<remote button>`"""
    words, n = list(words), 0
    for j in range(len(words) - 2):
        if words[j] in YB_SWAP and words[j + 1] == 0x41820008:
            ba, yb = YB_SWAP[words[j]]
            assert words[j + 2] == ba, hex(words[j + 2])
            words[j + 2] = yb
            n += 1
    assert n == 4, n
    return words


def relocate_vr(rev, kpadiread, dol, yb=False):
    delta = kpadiread - VR_USA_KPADIREAD
    extras = []
    for site, words in parse_vr(os.path.join(HERE, 'vr', 'RK5E01.txt')):
        words = list(words)
        for j in range(len(words) - 1):                       # the lis/ori pair that loads the helper's address
            if words[j] >> 16 == 0x3CC0 and words[j + 1] >> 16 == 0x60C6:
                assert ((words[j] & 0xFFFF) << 16 | (words[j + 1] & 0xFFFF)) == VR_ASPECT
                tgt = VR_ASPECT + delta
                words[j] = 0x3CC00000 | (tgt >> 16)
                words[j + 1] = 0x60C60000 | (tgt & 0xFFFF)
        if yb and site == VR_SITES['RK5E01'][3]:
            words = to_yb(words)
        site += delta
        orig = struct.unpack('>I', dol.read(site, 4))[0]
        assert words[-1] == 0 and orig in words, 'VR code does not contain the instruction at %08X' % site   # it runs it itself
        extras.append({'site': site, 'orig': orig, 'words': words[:-1]})   # the last word becomes the branch back
    assert [e['site'] for e in extras] == VR_SITES[rev], (rev, [hex(e['site']) for e in extras])
    return extras


def build_region(rev, ref, dol, debug_feed, yb=False):
    a = anchors.resolve(ref, dol)
    blob, syms = compile_region(a, debug_feed, yb)
    sites = []
    for name, key, _ in HOOKS:
        site = a[key]
        orig = struct.unpack('>I', dol.read(site, 4))[0]
        sites.append({'site': site, 'hook': syms['hook_' + name], 'orig': orig, 'name': name})
    extras = relocate_vr(rev, a['KPADiRead'], dol, yb)
    size = len(blob) + sum(4 * (len(e['words']) + 1) for e in extras)
    return {'base': BASE, 'blob': blob.hex(), 'state': syms['gc_state'], 'sites': sites, 'extras': extras,
            'addrs': a}, size


def main():
    debug_feed = '--debug-feed' in sys.argv
    ref = Dol(os.path.join(dol_dir(), 'RK5E01.dol'))
    out = {}
    for rev in REGIONS:
        dol = Dol(os.path.join(dol_dir(), rev + '.dol'))
        for yb in (False, True):
            key = rev + '-YB' if yb else rev
            out[key], n = build_region(rev, ref, dol, debug_feed, yb)
            print(key, '%d bytes' % n, {s['name']: '%08X' % s['site'] for s in out[key]['sites']},
                  'state %08X' % out[key]['state'])
            assert BASE + n <= 0x80003000, 'blob does not fit below the OS globals'
    name = 'patches_feed.json' if debug_feed else 'patches.json'
    json.dump(out, open(os.path.join(HERE, name), 'w'), indent=1)


if __name__ == '__main__':
    main()
