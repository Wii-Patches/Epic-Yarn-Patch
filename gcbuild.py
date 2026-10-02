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
HOOKS = [('poll', 'KPADiRead', 'POLL'), ('sample', 'Sample', 'SAMPLE'),
         ('probe', 'WPADProbe', 'PROBE'), ('post', 'Post', 'POST')]


def dol_dir():
    return os.environ.get('KEY_DOLS', 'dols')       # a directory of <REGION>.dol


def compile_region(a, debug_feed):
    src = os.path.join(HERE, 'src')
    tmp = tempfile.mkdtemp(prefix='gcpad')
    D = {
        'SI_TYPES': a['SiTypes'], 'SI_BUSY': a['SiBusy'], 'SI_SHADOW': a['SiShadow'],
        'FN_SIGETTYPE': a['SIGetType'], 'FN_OSDISABLE': a['OSDisableInterrupts'],
        'FN_OSRESTORE': a['OSRestoreInterrupts'], 'WPAD_TBL': a['WpadTbl'], 'SIDEWAYS': a['Sideways'],
    }
    rets = {'POLL_RET': a['KPADiRead'] + 4, 'SAMPLE_RET': a['Sample'] + 4,
            'PROBE_RET': a['WPADProbe'] + 4, 'POST_RET': a['Post'] + 4}
    defs = ['-D%s=0x%08Xu' % kv for kv in D.items()] + ['-DHOOK_' + h[2] for h in HOOKS]
    if debug_feed:
        defs.append('-DDEBUG_FEED')
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


def build_region(rev, ref, dol, debug_feed):
    a = anchors.resolve(ref, dol)
    blob, syms = compile_region(a, debug_feed)
    sites = []
    for name, key, _ in HOOKS:
        site = a[key]
        orig = struct.unpack('>I', dol.read(site, 4))[0]
        sites.append({'site': site, 'hook': syms['hook_' + name], 'orig': orig, 'name': name})
    return {'base': BASE, 'blob': blob.hex(), 'state': syms['gc_state'], 'sites': sites,
            'addrs': a}, len(blob)


def main():
    debug_feed = '--debug-feed' in sys.argv
    ref = Dol(os.path.join(dol_dir(), 'RK5E01.dol'))
    out = {}
    for rev in REGIONS:
        dol = Dol(os.path.join(dol_dir(), rev + '.dol'))
        out[rev], n = build_region(rev, ref, dol, debug_feed)
        print(rev, '%d bytes' % n, {s['name']: '%08X' % s['site'] for s in out[rev]['sites']},
              'state %08X' % out[rev]['state'])
        assert BASE + n <= 0x80003000, 'blob does not fit below the OS globals'
    name = 'patches_feed.json' if debug_feed else 'patches.json'
    json.dump(out, open(os.path.join(HERE, name), 'w'), indent=1)


if __name__ == '__main__':
    main()
