#!/usr/bin/env python3
"""Check patches.json against your own dumps of every region's sys/main.dol.

  KEY_DOLS=dir tools/verify.py        (dir holds RK5E01.dol RK5P01.dol RK5J01.dol RK5K01.dol)

For each region: the hook sites hold the instructions the patch expects, patching succeeds and a second patch is
refused, the patched DOL's sections are sane, and every site branches into the new section.
"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
sys.path.insert(0, HERE)
import patch_dol

ok = True
for rev, patch in json.load(open(os.path.join(HERE, '..', 'patches.json'))).items():
    path = os.path.join(os.environ.get('KEY_DOLS', 'dols'), rev.split('-')[0] + '.dol')
    data = open(path, 'rb').read()
    errs = []
    if patch_dol.state(data, patch) != 'unpatched':
        errs.append('not an unpatched %s main.dol' % rev)
    else:
        out = patch_dol.apply(data, patch)
        d = patch_dol.Dol(out)
        if patch_dol.state(out, patch) != 'patched':
            errs.append('patched DOL not recognised as patched')
        try:
            patch_dol.apply(out, patch)
            errs.append('a second patch was not refused')
        except patch_dol.PatchError:
            pass
        secs = sorted((a, a + s) for a, s in zip(d.addr, d.size) if s)
        if any(secs[i][1] > secs[i + 1][0] for i in range(len(secs) - 1)):
            errs.append('overlapping sections')
        base = patch['base']
        size = max(a + s - base for a, s in zip(d.addr, d.size) if a == base)
        if base + size > patch_dol.LIMIT:
            errs.append('code passes 0x%08X' % patch_dol.LIMIT)
        for s in patch['sites'] + patch['extras']:
            w = d.word(s['site'])
            tgt = s['site'] + (((w & 0x03FFFFFC) ^ 0x02000000) - 0x02000000)
            if w >> 26 != 18 or not base <= tgt < base + size:
                errs.append('site %08X does not branch into the new section' % s['site'])
    print('%s  %s' % (rev, 'ok' if not errs else 'FAIL: ' + '; '.join(errs)))
    ok &= not errs
sys.exit(0 if ok else 1)
