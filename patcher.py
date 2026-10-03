#!/usr/bin/env python3
"""Add GameCube controller support to a Kirby's Epic Yarn disc image.

  patcher.py <disc.wbfs|disc.iso>           patch the image in place (the original is kept as <name>.bak)
  patcher.py --layout yb <disc>             the Classic Controller code's Y/B layout instead of the default B/A
  patcher.py --check <disc.wbfs|disc.iso>   say which region it is and whether it is patched; change nothing

The image is extracted, its own sys/main.dol is patched for the disc's region (patch_dol.py) and the image is
rebuilt with wit.  It replaces the original *in place*, keeping its filename and folder -- USB loaders key off
the `/wbfs/<Title> [ID6]/` layout -- and the untouched original stays alongside as `<name>.bak`.
Only main.dol changes; the TMD, and the IOS it asks for, are left alone.
"""
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import patch_dol
from disc_ids import match_disc_id

WII_MAGIC = 0x5D1C9EA3
REGIONS = {
    'RK5E01': 'Kirby\'s Epic Yarn (USA)',
    'RK5P01': 'Kirby\'s Epic Yarn (Europe)',
    'RK5J01': 'Keito no Kirby (Japan)',
    'RK5K01': 'Teolsil Kirby Iyagi (Korea)',
}


LAYOUTS = {'ba': 'B/A (A jumps, B whips, X and Y are the remote\'s A and B)',
           'yb': 'Y/B (the Classic Controller code\'s Y/B mode; A jumps, B whips on the pad as well)'}


def resource(name):
    """a data file next to the sources, or inside a PyInstaller build"""
    if getattr(sys, 'frozen', False):
        return os.path.join(getattr(sys, '_MEIPASS', os.path.dirname(sys.executable)), name)
    return os.path.join(HERE, name)


def find_wit():
    """A wit bundled with this app (PyInstaller build) wins over PATH.

    --add-binary'd files land next to sys._MEIPASS, not next to the executable: a plain onedir build puts
    them in _internal/, and a windowed macOS .app puts them in Contents/Frameworks/.
    """
    name = 'wit.exe' if os.name == 'nt' else 'wit'
    if getattr(sys, 'frozen', False):
        for base in (getattr(sys, '_MEIPASS', None), os.path.dirname(sys.executable)):
            if base and os.path.isfile(os.path.join(base, name)):
                return os.path.join(base, name)
    return shutil.which('wit')


def read_disc_header(path):
    """(disc id, version) from a .wbfs or .iso, or None.

    A .wbfs keeps a copy of the disc header at 0x200; a plain .iso has it at 0.  Both are confirmed by the Wii
    magic word at header+0x18 rather than by the file extension, so a misnamed file is caught, not misread.
    """
    with open(path, 'rb') as f:
        for base in (0x200, 0x000):
            f.seek(base)
            head = f.read(0x20)
            if len(head) == 0x20 and struct.unpack_from('>I', head, 0x18)[0] == WII_MAGIC:
                return head[0:6].decode('ascii', 'replace'), head[7]
    return None


def load_patches():
    return json.load(open(resource('patches.json')))


def find_file(root, name):
    for r, _, files in os.walk(root):
        if name in files and os.path.basename(r) == 'sys':
            return os.path.join(r, name)
    return None


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError('%s failed:\n%s' % (os.path.basename(cmd[0]), (r.stderr or r.stdout).strip()))


def identify(image):
    got = read_disc_header(image)
    if not got:
        raise RuntimeError('%s is not a Wii disc image (.wbfs or .iso)' % os.path.basename(image))
    disc_id, version = got
    region = match_disc_id(disc_id, REGIONS)
    if region is None:
        raise RuntimeError('%s is not Kirby\'s Epic Yarn (disc id %s).\n\nSupported: %s'
                           % (os.path.basename(image), disc_id, ', '.join(sorted(REGIONS))))
    return region


def patch_key(disc_id, layout='ba'):
    return disc_id + ('-YB' if layout == 'yb' else '')


def check(image, log=print):
    """'unpatched', 'patched' or 'mismatch' for the disc's main.dol"""
    disc_id = identify(image)
    wit = find_wit()
    if wit is None:
        raise RuntimeError('wit (Wiimms ISO Tool) not found: not bundled with this build and not on PATH')
    patch = load_patches()[disc_id]
    with tempfile.TemporaryDirectory(prefix='kirby_check_') as tmp:
        run([wit, 'extract', image, '--dest', tmp, '--psel', 'data', '--files', '+/sys/main.dol',
             '--overwrite', '-q'])
        dol = find_file(tmp, 'main.dol')
        if not dol:
            raise RuntimeError('no sys/main.dol in the disc')
        return disc_id, patch_dol.state(open(dol, 'rb').read(), patch)


def run_patch(image, log=print, layout='ba'):
    """Patch `image` in place.  Returns the path; raises RuntimeError with a message fit for the user."""
    disc_id = identify(image)
    wit = find_wit()
    if wit is None:
        raise RuntimeError('wit (Wiimms ISO Tool) not found: not bundled with this build and not on PATH')
    patch = load_patches()[patch_key(disc_id, layout)]
    fmt = '--iso' if image.lower().endswith('.iso') else '--wbfs'
    folder = os.path.dirname(os.path.abspath(image))
    log('disc: %s -> %s' % (disc_id, REGIONS[disc_id]))
    log('layout: %s' % LAYOUTS[layout])

    # the extracted disc and the rebuilt image both sit next to the original: make sure they fit first
    need = int(os.path.getsize(image) * 2.2) + (1 << 30)
    if shutil.disk_usage(folder).free < need:
        raise RuntimeError('not enough free space in %s: about %d GB is needed while patching'
                           % (folder, need >> 30))

    try:
        tmpdir = tempfile.TemporaryDirectory(prefix='.kirby_patch_', dir=folder)
    except OSError:                                    # a read-only or odd folder: fall back to the system's
        tmpdir = tempfile.TemporaryDirectory(prefix='kirby_patch_')
    with tmpdir as tmp:
        fst = os.path.join(tmp, 'fst')
        log('extracting %s (a few minutes)...' % os.path.basename(image))
        run([wit, 'extract', image, '--dest', fst, '--psel', 'data', '--overwrite', '-q'])

        dol_path = find_file(fst, 'main.dol')
        if not dol_path:
            raise RuntimeError('could not find sys/main.dol in the extracted disc')
        data = open(dol_path, 'rb').read()
        try:
            data = patch_dol.apply(data, patch)
        except patch_dol.PatchError as e:
            raise RuntimeError(str(e))
        open(dol_path, 'wb').write(data)
        log('  patched main.dol')

        staged = os.path.join(tmp, 'patched.img')
        log('rebuilding the image...')
        run([wit, 'copy', fst, '--dest', staged, fmt, '--overwrite', '-q'])

        # Only touch the user's file once the rebuild has actually succeeded.
        backup = image + '.bak'
        if os.path.exists(backup):
            log('  backup already exists, keeping it: %s' % os.path.basename(backup))
        else:
            os.replace(image, backup)
            log('  original kept as %s' % os.path.basename(backup))
        try:
            shutil.move(staged, image)
        except Exception:
            if not os.path.exists(image) and os.path.exists(backup):
                os.replace(backup, image)              # put the original back rather than lose it
            raise
        log('done: patched in place, %s' % os.path.basename(image))
    return image


def main(argv):
    if len(argv) == 2 and argv[0] == '--check':
        disc_id, st = check(argv[1])
        print('%s  %s  main.dol: %s' % (disc_id, REGIONS[disc_id], st))
        return 0 if st != 'mismatch' else 1
    layout = 'ba'
    if len(argv) == 3 and argv[0] == '--layout' and argv[1].lower() in LAYOUTS:
        layout, argv = argv[1].lower(), argv[2:]
    if len(argv) != 1 or argv[0].startswith('-'):
        print(__doc__)
        return 2
    try:
        run_patch(argv[0], layout=layout)
    except RuntimeError as e:
        print('ERROR: %s' % e, file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
