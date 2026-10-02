#!/usr/bin/env python3
import json, os, socket, sys
SOCK = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.srv.sock')

def call(req):
    s = socket.socket(socket.AF_UNIX)
    s.connect(SOCK)
    s.sendall((json.dumps(req) + '\n').encode())
    return s.makefile().read().strip()

if __name__ == '__main__':
    a = sys.argv[1:]
    ch = None
    if a and a[0].startswith('ch='):      # gcctl.py ch=1 pad A
        ch = int(a[0][3:]); a = a[1:]
    if a[0] == 'pad':
        print(call({'cmd': 'set', 'spec': a[1], 'secs': float(a[2]) if len(a) > 2 else 0, 'ch': ch}))
    elif a[0] == 'set':
        print(call({'cmd': 'set', 'spec': a[1], 'ch': ch}))
    elif a[0] == 'snap':
        print(call({'cmd': 'snap', 'name': a[1], 'wait': float(a[2]) if len(a) > 2 else 1.0}))
    elif a[0] == 'peek':
        print(call({'cmd': 'peek', 'ch': ch}))
    elif a[0] == 'mem':
        print(call({'cmd': 'mem', 'addr': a[1], 'n': int(a[2])}))
    elif a[0] == 'wait':
        import time; time.sleep(float(a[1]))
    elif a[0] == 'quit':
        print(call({'cmd': 'quit'}))
