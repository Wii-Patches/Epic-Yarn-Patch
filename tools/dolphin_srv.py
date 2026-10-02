#!/usr/bin/env python3
"""A long-running Dolphin session for testing the DEBUG_FEED build interactively.

  dolphin_srv.py <image> &          start Dolphin (no Wii Remote) and listen on tools/.srv.sock
  gcctl.py pad A [secs]             hold a pad state for secs (default: until changed), then neutral
  gcctl.py set A,stk=1,0            hold a combined state
  gcctl.py snap name                save the current frame to shots/name.png and print the game's pad status
  gcctl.py peek                     print the game's pad status
  gcctl.py quit

The pad response is written into gc_state.feed[] over Dolphin's GDB stub.
"""
import glob, json, os, shutil, socket, struct, subprocess, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import dolphin_gc as dg
from gdbmem import Gdb

SOCK = os.path.join(HERE, '.srv.sock')
SHOTS = os.environ.get('SHOTS', os.path.join(HERE, '..', 'shots'))


def compose(spec):
    """'A,stk=1,0' style spec -> (hi, lo) response words.  Parts: buttons, stk=x:y, cst=x:y, lt=0..1, rt=0..1"""
    h, l = 0x00808080, 0x80800000
    for part in spec.split(','):
        if not part or part == 'N':
            continue
        if part in dg.BTN:
            h |= dg.BTN[part]
        elif part.startswith('stk='):
            x, y = [float(v) for v in part[4:].split(':')]
            h = (h & ~0xFFFF) | (int(128 + 127 * x) << 8) | int(128 + 127 * y)
        elif part.startswith('cst='):
            x, y = [float(v) for v in part[4:].split(':')]
            l = (l & 0x0000FFFF) | (int(128 + 127 * x) << 24) | (int(128 + 127 * y) << 16)
        else:
            raise ValueError(part)
    return h, l


def main():
    image = sys.argv[1]
    chan = int(os.environ.get('CHAN', '0'))
    patches = json.load(open(os.path.join(HERE, '..', os.environ.get('PATCHES', 'patches_feed.json'))))
    region = patches[os.environ.get('REGION', 'RK5E01')]
    feed = region['state'] + chan * 8
    gamepad = region['addrs']['GamePad']
    user = os.path.abspath(os.environ.get('USERDIR', os.path.join(HERE, '..', 'dolphin_user')))
    dg.prepare(user, wipe=not os.environ.get('KEEPUSER'))
    os.makedirs(SHOTS, exist_ok=True)
    subprocess.check_call(['open', '-n', '-a', '/Applications/Dolphin.app', '--args', '-b', '-u', user, '-e', image,
                           '-v', os.environ.get('VIDEO', 'Metal')])
    time.sleep(2)
    g = None
    for _ in range(120):
        try:
            g = Gdb(timeout=30)
            break
        except OSError:
            time.sleep(1)
    g.cont()
    time.sleep(1)
    if not os.environ.get('REALSI'):
        g.interrupt()
        g.cmd('M%x,8:%s' % (feed, struct.pack('>II', *compose('N')).hex()))   # a neutral pad on the first channel
        g.cont()
    if os.path.exists(SOCK):
        os.unlink(SOCK)
    srv = socket.socket(socket.AF_UNIX)
    srv.bind(SOCK)
    srv.listen(4)
    print('ready', flush=True)

    pipe = [None]
    held = set()

    def setpipe(spec):
        """REALSI: drive Dolphin's emulated GC pad on port 1 through its Pipe device"""
        if pipe[0] is None:
            pipe[0] = os.open(os.path.join(user, 'Pipes', 'gc'), os.O_WRONLY | os.O_NONBLOCK)
        names = dict(A='A', B='B', X='X', Y='Y', Z='Z', S='START', L='L', R='R', U='D_UP', D='D_DOWN', LT='D_LEFT',
                     RT='D_RIGHT')
        want, main, cst = set(), (0.5, 0.5), (0.5, 0.5)
        for part in spec.split(','):
            if part in names:
                want.add(names[part])
            elif part.startswith('stk='):
                x, y = [float(v) for v in part[4:].split(':')]
                main = (0.5 + x / 2, 0.5 + y / 2)
            elif part.startswith('cst='):
                x, y = [float(v) for v in part[4:].split(':')]
                cst = (0.5 + x / 2, 0.5 + y / 2)
        lines = ['RELEASE %s' % b for b in held - want] + ['PRESS %s' % b for b in want - held]
        lines += ['SET MAIN %.3f %.3f' % main, 'SET C %.3f %.3f' % cst]
        held.clear()
        held.update(want)
        os.write(pipe[0], ('\n'.join(lines) + '\n').encode())

    def setpad(h, l, ch=None):
        g.interrupt()
        g.cmd('M%x,8:%s' % (feed + 8 * ((ch if ch is not None else chan) - chan), struct.pack('>II', h, l).hex()))
        g.cont()

    def frames():
        return sorted(glob.glob(os.path.join(user, 'Dump', 'Frames', '**', '*.png'), recursive=True),
                      key=os.path.getmtime)

    try:
        while True:
            c, _ = srv.accept()
            req = json.loads(c.makefile().readline())
            cmd, out = req['cmd'], ''
            try:
                if cmd == 'set':
                    ch = req.get('ch')
                    if os.environ.get('REALSI'):
                        setpipe(req['spec'])
                    else:
                        setpad(*compose(req['spec']), ch=ch)
                    if req.get('secs'):
                        time.sleep(req['secs'])
                        if os.environ.get('REALSI'):
                            setpipe('N')
                        else:
                            setpad(*compose('N'), ch=ch)
                elif cmd in ('peek', 'snap'):
                    time.sleep(req.get('wait', 1.0))
                    if cmd == 'snap':
                        fs = frames()
                        if fs:
                            shutil.copy(fs[-2] if len(fs) > 1 else fs[-1], os.path.join(SHOTS, req['name'] + '.png'))
                            for f in fs[:-30]:           # keep the dump folder small
                                os.unlink(f)
                    g.interrupt()
                    out = dg.pad_status(g, req.get('ch') if req.get('ch') is not None else chan, gamepad)
                    g.cont()
                elif cmd == 'mem':
                    g.interrupt()
                    out = g.read_mem(int(req['addr'], 16), req['n']).hex()
                    g.cont()
                elif cmd == 'quit':
                    c.sendall(b'bye\n')
                    break
            except Exception as e:             # keep the session alive
                out = 'error: %r' % e
            c.sendall((out + '\n').encode())
            c.close()
    finally:
        dg.stop(user)
        if os.path.exists(SOCK):
            os.unlink(SOCK)


if __name__ == '__main__':
    main()
