#!/usr/bin/env python3
"""Kirby-Patcher: drop a Kirby's Epic Yarn disc image on the window, done.

Adds GameCube controller support (ports 1-4).  See patcher.py for what happens to the image: it is patched
in place, and the untouched original is kept next to it as <name>.bak.
"""
import os
import queue
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import patcher

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    HAVE_DND = True
except ImportError:                                    # fall back to click-to-browse
    HAVE_DND = False

BASE = TkinterDnD.Tk if HAVE_DND else tk.Tk


class App(BASE):
    def __init__(self):
        super().__init__()
        self.title('Kirby-Patcher')
        self.geometry('600x440')
        self.msgq = queue.Queue()
        self.busy = False
        try:
            self.iconphoto(True, tk.PhotoImage(file=patcher.resource(os.path.join('assets', 'icon.png'))))
        except Exception:                              # the window icon is a nicety
            pass

        tk.Label(self, text="Kirby's Epic Yarn: GameCube controller support",
                 font=('TkDefaultFont', 13, 'bold')).pack(pady=(12, 0))
        hint = ('Drop a .wbfs or .iso here\n\n(or click to choose one)'
                if HAVE_DND else 'Click to choose a .wbfs or .iso')
        self.drop = tk.Label(self, text=hint, relief='ridge', bd=2, padx=10, pady=30, cursor='hand2')
        self.drop.pack(fill='x', padx=10, pady=10)
        self.drop.bind('<Button-1>', lambda e: self.pick())
        if HAVE_DND:
            self.drop.drop_target_register(DND_FILES)
            self.drop.dnd_bind('<<Drop>>', self.on_drop)

        tk.Label(self, text='USA, Europe, Japan and Korea discs. The original is kept alongside as <name>.bak',
                 fg='#666').pack()

        self.log = tk.Text(self, height=12, state='disabled', wrap='word')
        self.log.pack(fill='both', expand=True, padx=10, pady=10)
        self.after(100, self.poll_queue)

    def on_drop(self, event):
        paths = self.tk.splitlist(event.data)          # handles {braced paths with spaces}
        if paths:
            self.start(paths[0])

    def pick(self):
        if self.busy:
            return
        p = filedialog.askopenfilename(title='Select disc image',
                                       filetypes=[('Wii disc image', '*.wbfs *.iso'), ('All files', '*')])
        if p:
            self.start(p)

    def append_log(self, text):
        self.log.configure(state='normal')
        self.log.insert('end', text + '\n')
        self.log.see('end')
        self.log.configure(state='disabled')

    def poll_queue(self):
        try:
            while True:
                kind, payload = self.msgq.get_nowait()
                if kind == 'log':
                    self.append_log(payload)
                elif kind == 'done':
                    ok, msg = payload
                    self.busy = False
                    self.drop.configure(state='normal')
                    if ok:
                        messagebox.showinfo('Done', 'Patched in place:\n%s' % msg)
                    else:
                        messagebox.showerror('Patch failed', msg)
        except queue.Empty:
            pass
        self.after(100, self.poll_queue)

    def work(self, image):
        try:
            patcher.run_patch(image, lambda t: self.msgq.put(('log', t)))
            self.msgq.put(('done', (True, image)))
        except Exception as e:
            self.msgq.put(('log', 'ERROR: %s' % e))
            self.msgq.put(('done', (False, str(e))))

    def start(self, image):
        if self.busy:
            return
        if not os.path.isfile(image):
            messagebox.showerror('Not a file', '%s is not a file.' % image)
            return
        self.busy = True
        self.drop.configure(state='disabled')
        self.log.configure(state='normal')
        self.log.delete('1.0', 'end')
        self.log.configure(state='disabled')
        threading.Thread(target=self.work, args=(image,), daemon=True).start()


if __name__ == '__main__':
    App().mainloop()
