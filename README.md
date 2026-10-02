# Epic-Yarn-Patch

A patcher for *Kirby's Epic Yarn* (Wii) that adds **GameCube controller support**: play with a GameCube pad
in ports 1-4, no Wii Remote needed.

Works with the USA, Europe, Japan and Korea discs.

## What you need

- A dump of your own game as a `.wbfs` or `.iso`. No game files are included here.
- A Wii (or Dolphin) that can run it from a USB loader or SD card.
- A GameCube controller. Ports 1-4 are players 1-4 (the game uses two).
- **Cheats off**: when launching from a USB loader, turn off cheat codes and the code handler / debugger for
  the patched disc. They load into the same memory the patch uses.
- **To run the patcher**: nothing else. The release builds bundle everything they need. (Running from source
  needs Python 3, [Wiimms ISO Tool](https://wit.wiimm.de/) and, optionally, `tkinterdnd2`.)

## How to use it

1. **Download** `Kirby-Patcher` for your platform from Releases (or run `python3 gui.py`).
   The apps are unsigned, so your OS will warn you. On macOS, right-click the app and choose Open.
2. **Pick a layout** (B/A or Y/B, see Controls), then **drop your `.wbfs` or `.iso` on the window.**
3. **Wait for "done: patched in place".** It takes a few minutes: the patcher reads the disc's own ID, patches
   the matching `main.dol` and rebuilds the image. Your original is kept as `<name>.bak`.
4. **Copy the image back** to your USB drive or SD card and play.

No window? `python3 patcher.py "Kirby's Epic Yarn (USA).wbfs"` does the same, and
`python3 patcher.py --layout yb <image>` for the Y/B layout, and
`python3 patcher.py --check <image>` says which region a disc is and whether it is already patched.

It needs about twice the image's size free in the image's folder while it works. The patcher refuses a disc it
doesn't recognize or that was already patched, rather than guess.

## Controls

The pad takes the place of a Classic Controller, and the Classic Controller code (below) turns that into what the
game expects from the Wii Remote. Two layouts are offered (Vague Rant and crediar's B/A and Y/B modes); the GameCube
mapping is chosen so **A jumps and B whips in both**. The table is the B/A layout:

| GameCube | Classic Controller | Wii Remote | In the game |
| --- | --- | --- | --- |
| Control stick | Left stick | D-pad, pointer | Move; moves the pointer in menus and Kirby's Pad |
| D-pad | D-pad | D-pad | Move, crouch, enter doors (up) |
| A | A | 2 | Jump, confirm |
| B | B | 1 | Yarn whip, cancel |
| X | X | A | Menu actions; summon Angie in co-op |
| Y | Y | B | Customization menu, cancel |
| L | L | 2 | Jump |
| R | R | 1 | Yarn whip |
| Start | + | + | Pause |
| Z | − | − | The controls screen for the current form |
| C-stick | Right stick | Tilt, pointer | Aim the Tankbot and the Fire Engine, point |

In the Y/B layout the Classic Controller's B jumps and Y whips, so the pad's A and B are sent there and X and Y
become its A and X (the remote's A and B). On the pad itself nothing changes for jumping and whipping.

Left and right on the C-stick tilt the remote. There is no HOME button on a GameCube pad, so the HOME Menu still
needs a Wii Remote. A Wii Remote that *is* connected keeps working alongside the pad.

## Supported discs

| Disc ID  | Version                                  |
|----------|------------------------------------------|
| `RK5E01` | Kirby's Epic Yarn (USA)                  |
| `RK5P01` | Kirby's Epic Yarn (Europe)               |
| `RK5J01` | Keito no Kirby (Japan)                   |
| `RK5K01` | Teolsil Kirby Iyagi (Korea)              |

## What was tested

- **Dolphin**, USA disc, on a build that feeds the pad's responses in by hand: the game boots with no Wii Remote
  connected and sees a Classic Controller; the save prompt, title screen, file select, the intro and its skip
  prompt, the dialogue, and walking (stick and D-pad), jumping and the yarn whip in Quilty Square all work from
  the pad; the C-stick's tilt and pointer values reach the game.
- **Dolphin**, Europe, Japan and Korea, same hand-fed build: each boots with no Wii Remote, sees the Classic
  Controller, takes A and B as the remote's 2 and 1, and gets through the save prompt, title screen and file select
  to the first stage's loading screen from the pad. Walking, jumping and the whip were only played on the USA disc.
- **The patcher** (`patcher.py`) on a copy of the USA `.wbfs`: it patches and rebuilds the image, refuses to patch it
  twice, and Dolphin's emulated GameCube pad is detected on the result through the real Serial Interface path.
  The other regions' discs were not run through the patcher itself, only checked by `tools/verify.py`.

- **Y/B layout**, USA, same hand-fed Dolphin build: the pad's A and B reach the game as the remote's 2 and 1, X and Y
  as A and B, L/R, Start and Z as in B/A. Its code differs from B/A in four constants, checked against the published Y/B
  code. It was not played through, and the other regions' Y/B builds were only checked by `tools/verify.py`.

Not tested: a real console, aiming the Tankbot and the Fire Engine, and the pointer in Kirby's Pad.

## How it works

Epic Yarn links the SI library but not PAD, so nothing ever polls a GameCube pad. The patch (`src/gcpad.c`,
in a new DOL section at `0x80001820`) lies to the game's Wii Remote library instead, in two layers.

**The pad as a Classic Controller** (three hooks of our own):

| Hook | Site | What it does |
| --- | --- | --- |
| `gc_poll` | `KPADiRead` entry | Turns on the Serial Interface's own auto-polling for the channel, handles hot-plug (the approach is [Barrel Blast Patch](https://github.com/quatric/Barrel-Blast-Patch)'s, which runs on a console) |
| `gc_sample` | `KPADiRead`, the "any samples queued?" check | Queues a Classic Controller sample holding the pad's buttons and sticks |
| `gc_probe` | `WPADProbe` entry | Reports a connected Classic Controller while a pad is plugged in and no remote is |

**Classic Controller Support (B/A mode) v1.1** by Vague Rant and crediar turns that into the game's own controls:
the button injector, the pointer hack (left and right stick) and the accelerometer hack (right stick tilt). It is
published for each region; `vr/RK5E01.txt` is the USA code, and `gcbuild.py` moves it to the others by
`KPADiRead`'s offset and checks the result against every region's published sites. The patcher writes both layers
into a new DOL section and replaces each hook instruction with a branch to its body.

The hook addresses are found once in the USA `main.dol` and located in the other regions by matching masked
windows of code (`tools/anchors.py`), never by guessing.

## Building from source

```sh
KEY_DOLS=dir python3 gcbuild.py     # needs devkitPPC and your own dumps: dir/RK5E01.dol RK5P01.dol RK5J01.dol RK5K01.dol
KEY_DOLS=dir python3 tools/verify.py
python3 patch_dol.py RK5E01 main.dol main.patched.dol      # patch a bare main.dol
./build_gui.sh                       # the standalone app (PyInstaller)
```

`patches.json` is checked in: it holds only this project's code, Vague Rant and crediar's, and the instructions it
expects at the hook sites, never the game itself, so only developers need devkitPPC or the DOLs. `gcbuild.py --debug-feed` builds a
test variant whose pad reads come from memory instead of the SI hardware; `tools/dolphin_srv.py` and
`tools/gcctl.py` drive it in Dolphin over the GDB stub (see their docstrings).

## Help

No support will be provided for this tool.

## Credits

- **Vague Rant and crediar**: *Classic Controller Support v1.1* for Kirby's Epic Yarn, which does the real work of
  turning a Classic Controller into the game's controls (buttons, pointer, tilt). Their code is used as published.
- The SI polling and hot-plug handling, and the idea of lying to KPAD, come from
  [Barrel Blast Patch](https://github.com/quatric/Barrel-Blast-Patch) and
  [ACCF-Patch](https://github.com/quatric/ACCF-Patch).
- Wiimm: [wit / Wiimms ISO Tools](https://wit.wiimm.de/)

## License

Copyright (c) 2026 quatric
