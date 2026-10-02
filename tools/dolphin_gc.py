#!/usr/bin/env python3
"""Run Kirby's Epic Yarn in Dolphin with the DEBUG_FEED build and a scripted GameCube pad, no Wii Remote,
and read the game's pad state back over the GDB stub.

  dolphin_gc.py <image|extracted disc dir> <steps>      env: USERDIR, PATCHES (patches_feed.json), REGION

steps: comma list of  <seconds>:<name> ; each is applied that many seconds after the game started
  name = a button (A B X Y Z S L R U D LT RT), N (neutral), or stk=<x>,<y> / cst=<x>,<y> with -1..1
The pad response is written straight into gc_state.feed[] (the DEBUG_FEED build reads it instead of the SI
hardware), which exercises the whole KPAD/WPAD side deterministically.  Frames are dumped at every step.
"""
import glob, json, os, shutil, struct, subprocess, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from gdbmem import Gdb

DOLPHIN = '/Applications/Dolphin.app/Contents/MacOS/Dolphin'
PORT = 2159
GAME_PAD = 0x808FC4C0          # the game's own per-channel status array (0xF0 each), USA

BTN = dict(A=0x01000000, B=0x02000000, X=0x04000000, Y=0x08000000, S=0x10000000, Z=0x00100000, L=0x00400000,
           R=0x00200000, U=0x00080000, D=0x00040000, LT=0x00010000, RT=0x00020000)


def state(name):
    h, l = 0x00808080, 0x80800000          # neutral: pad present (bit 23), sticks centred
    if name in BTN:
        h |= BTN[name]
    elif name.startswith('stk='):
        x, y = [float(v) for v in name[4:].split(',')]
        h = (h & ~0xFFFF) | (int(128 + 127 * x) << 8) | int(128 + 127 * y)
    elif name.startswith('cst='):
        x, y = [float(v) for v in name[4:].split(',')]
        l = (int(128 + 127 * x) << 24) | (int(128 + 127 * y) << 16)
    return h, l


def prepare(user, wipe=True):
    if wipe:
        shutil.rmtree(user, ignore_errors=True)
    os.makedirs(os.path.join(user, 'Config'), exist_ok=True)
    open(os.path.join(user, 'Config', 'Dolphin.ini'), 'w').write(
        "[General]\nGDBPort = %d\n[Interface]\nConfirmStop = False\nUsePanicHandlers = False\n"
        "[Core]\nMMU = True\nCPUThread = False\nCPUCore = 4\nEnableDebugging = True\n"
        "WiimoteContinuousScanning = False\nWiimoteControllerInterface = False\n"
        "[DSP]\nBackend = No Audio Output\n"
        "[Analytics]\nPermissionAsked = True\nEnabled = False\n" % PORT +
        ("[Movie]\nDumpFrames = True\nDumpFramesSilent = True\nDumpFramesAsImages = True\n"
         if os.environ.get('FRAMEDUMP') else ""))
    if os.environ.get('REALSI'):
        # a GameCube pad on port 1 through Dolphin's own SI emulation: the unpatched hardware path.  Input goes
        # in through the Pipe device (Pipes/gc): PRESS A / SET MAIN x y lines
        os.makedirs(os.path.join(user, 'Pipes'), exist_ok=True)
        if not os.path.exists(os.path.join(user, 'Pipes', 'gc')):
            os.mkfifo(os.path.join(user, 'Pipes', 'gc'))
        ini = open(os.path.join(user, 'Config', 'Dolphin.ini')).read().replace(
            '[Core]\n', '[Core]\nSIDevice0 = 6\nSIDevice1 = 0\n')
        open(os.path.join(user, 'Config', 'Dolphin.ini'), 'w').write(ini)
        open(os.path.join(user, 'Config', 'GCPadNew.ini'), 'w').write(
            "[GCPad1]\nDevice = Pipe/0/gc\n" + "".join("Buttons/%s = `Button %s`\n" % (b, b) for b in 'ABXYZ') +
            "Buttons/Start = `Button START`\n" +
            "".join("D-Pad/%s = `Button D_%s`\n" % (d.title(), d.upper()) for d in ('up', 'down', 'left', 'right')) +
            "Triggers/L = `Button L`\nTriggers/R = `Button R`\n"
            "Main Stick/Up = `Axis MAIN Y +`\nMain Stick/Down = `Axis MAIN Y -`\n"
            "Main Stick/Left = `Axis MAIN X -`\nMain Stick/Right = `Axis MAIN X +`\n"
            "C-Stick/Up = `Axis C Y +`\nC-Stick/Down = `Axis C Y -`\n"
            "C-Stick/Left = `Axis C X -`\nC-Stick/Right = `Axis C X +`\n")
    open(os.path.join(user, 'Config', 'WiimoteNew.ini'), 'w').write(
        "[Wiimote1]\nSource = %d\n" % (2 if os.environ.get('REALMOTE') else 0))


def pid(user):
    out = subprocess.run(['ps', '-axo', 'pid=,command='], capture_output=True, text=True).stdout
    for ln in out.splitlines():
        if user in ln and 'Dolphin' in ln and 'dolphin_gc' not in ln:
            return int(ln.split()[0])


def stop(user):
    p = pid(user)
    if p:
        os.kill(p, 15)
        time.sleep(2)
        if pid(user):
            os.kill(pid(user), 9)


def pad_status(g, chan=0, base=GAME_PAD):
    b = g.read_mem(base + chan * 0xF0, 0x70)
    hold, trig, rel = struct.unpack('>III', b[0:12])
    acc = struct.unpack('>fff', b[0xC:0x18])
    pos = struct.unpack('>ff', b[0x20:0x28])
    dev, err, dpd, fmt = b[0x5C], b[0x5D], b[0x5E], b[0x5F]
    return ('hold=%04X trig=%04X rel=%04X acc=(%.2f %.2f %.2f) pos=(%.2f %.2f) dev=%d err=%d dpd=%d fmt=%d'
            % (hold, trig, rel, *acc, *pos, dev, err, dpd, fmt))


def main():
    image, steps = sys.argv[1:3]
    patches = json.load(open(os.path.join(HERE, '..', os.environ.get('PATCHES', 'patches_feed.json'))))
    st = patches[os.environ.get('REGION', 'RK5E01')]['state']
    feed = st                                       # struct st { u32 feed[8]; ... }
    user = os.path.abspath(os.environ.get('USERDIR', os.path.join(HERE, '..', 'dolphin_user')))
    prepare(user)
    video = os.environ.get('VIDEO', 'Metal')
    subprocess.check_call(['open', '-n', '-a', '/Applications/Dolphin.app', '--args', '-b', '-u', user, '-e', image,
                           '-v', video])
    time.sleep(2)
    g = None
    for _ in range(120):
        try:
            g = Gdb(timeout=30)
            break
        except OSError:
            time.sleep(1)
    if g is None:
        sys.exit('no GDB stub')
    g.cont()
    t0 = time.time()
    plan = [(float(a), b) for a, b in (s.split(':', 1) for s in steps.split(','))]
    out = os.environ.get('OUT', 'shot')
    marks = []
    try:
        for t, name in plan:
            while time.time() - t0 < t:
                time.sleep(0.2)
            if name != 'peek':
                h, l = state(name)
                g.interrupt()
                g.cmd('M%x,10:%s' % (feed, struct.pack('>IIII', h, l, 0, 0).hex()))
                g.cont()
            time.sleep(1.5)
            g.interrupt()
            print('%6.1fs %-12s %s' % (time.time() - t0, name, pad_status(g)))
            g.cont()
            frames = sorted(glob.glob(os.path.join(user, 'Dump', 'Frames', '**', '*.png'), recursive=True),
                            key=os.path.getmtime)
            marks.append((t, name, len(frames)))
        time.sleep(2)
    finally:
        frames = sorted(glob.glob(os.path.join(user, 'Dump', 'Frames', '**', '*.png'), recursive=True),
                        key=os.path.getmtime)
        for i, (t, name, n) in enumerate(marks):
            k = min(n + 20, len(frames) - 1)
            if frames and k >= 0:
                shutil.copy(frames[k], '%s_%02d_%s.png' % (out, i, name.replace('=', '').replace(',', '_')))
        stop(user)
        print('frames', len(frames))


if __name__ == '__main__':
    main()
