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
2. **Drop your `.wbfs` or `.iso` on the window.**
3. **Wait for "done: patched in place".** It takes a few minutes: the patcher reads the disc's own ID, patches
   the matching `main.dol` and rebuilds the image. Your original is kept as `<name>.bak`.
4. **Copy the image back** to your USB drive or SD card and play.

No window? `python3 patcher.py "Kirby's Epic Yarn (USA).wbfs"` does the same, and
`python3 patcher.py --check <image>` says which region a disc is and whether it is already patched.

It needs about twice the image's size free in the image's folder while it works. The patcher refuses a disc it
doesn't recognize or that was already patched, rather than guess.

## Controls

The game is played with the Wii Remote held sideways. The pad takes the place of that remote:

| GameCube | Wii Remote (sideways) | In the game |
| --- | --- | --- |
| Control stick / D-pad | D-pad | Move, crouch, enter doors (up), transform (tap left/right twice) |
| A, X | 2 | Jump, confirm |
| B, Y | 1 | Yarn whip, cancel |
| R | A | Click with the pointer, select; summon Angie in co-op |
| L | − | The controls screen for the current form |
| Start | + | Pause / menu |
| C-stick | Pointer and tilt | Move the cursor in the menus and in Kirby's Pad / Quilty Court; aim the Tankbot and the Fire Engine; draw the Train's tracks |
| Z | Shake | The second player's boost in the Spin Boarder and Off-Roader |

There is no HOME button on a GameCube pad, so the HOME Menu still needs a Wii Remote. A Wii Remote that *is*
connected keeps working alongside the pad (its buttons and the pad's are combined).

## Supported discs

| Disc ID  | Version                                  |
|----------|------------------------------------------|
| `RK5E01` | Kirby's Epic Yarn (USA)                  |
| `RK5P01` | Kirby's Epic Yarn (Europe)               |
| `RK5J01` | Keito no Kirby (Japan)                   |
| `RK5K01` | Teolsil Kirby Iyagi (Korea)              |

## What was tested

- **Dolphin**, USA disc, on a build that feeds the pad's responses in by hand: the game boots with no Wii Remote
  connected, the pad is accepted as player 1 (and 2 and 3), and the save prompt, title screen, file select, the
  intro and its skip prompt, the dialogue, and walking, jumping and the yarn whip in Quilty Square all work from
  the pad. The D-pad turns the right way in the menus and in the game.
- **Dolphin**, the real patched `.wbfs` that `patcher.py` writes, with Dolphin's emulated GameCube pad: the pad
  is detected through the Serial Interface and shows up in the game as a connected remote.
- **Dolphin**, the Europe, Japan and Korea discs on the same hand-fed build: each boots with no Wii Remote and
  accepts the pad (A arrives as the remote's 2 button). `tools/verify.py` also checks every region's hook sites.

Not tested yet: a real console, the Tankbot / Fire Engine aiming directions (the tilt axes are a best guess from
the game's code), and the pointer in Kirby's Pad.

## How it works

Epic Yarn links the SI library but not PAD, so nothing ever polls a GameCube pad. The patch (`src/gcpad.c`,
about 4 KB of PowerPC in a new DOL section at `0x80001820`) lies to the game's Wii Remote library instead:

| Hook | Site | What it does |
| --- | --- | --- |
| `gc_poll` | `KPADiRead` entry | Turns on the Serial Interface's own auto-polling for the channel, handles hot-plug (the approach is [Barrel Blast Patch](https://github.com/quatric/Barrel-Blast-Patch)'s, which runs on a console) |
| `gc_sample` | `KPADiRead`, the "any samples queued?" check | Queues a bare-Wii-Remote sample holding the pad's buttons, with the D-pad turned the way the game expects for a sideways remote |
| `gc_probe` | `WPADProbe` entry | Reports a connected Wii Remote while a pad is plugged in and no remote is |
| `gc_post` | `KPADiRead` return | Writes the C-stick into the returned status as a pointer and as acceleration (tilt, and a shake for Z) |

The game never learns a pad is involved: it calls `KPADRead` once per channel per frame and gets a Wii Remote.
The patcher adds the section to the DOL header, replaces the four hook instructions with branches, and each
stub runs the instruction it replaced and branches back.

The hook addresses are found once in the USA `main.dol` and located in the other regions by matching masked
windows of code (`tools/anchors.py`), never by guessing.

## Building from source

```sh
KEY_DOLS=dir python3 gcbuild.py     # needs devkitPPC and your own dumps: dir/RK5E01.dol RK5P01.dol RK5J01.dol RK5K01.dol
KEY_DOLS=dir python3 tools/verify.py
python3 patch_dol.py RK5E01 main.dol main.patched.dol      # patch a bare main.dol
./build_gui.sh                       # the standalone app (PyInstaller)
```

`patches.json` is checked in: it holds only this project's code and the four instructions it expects at the hook
sites, never the game itself, so only developers need devkitPPC or the DOLs. `gcbuild.py --debug-feed` builds a
test variant whose pad reads come from memory instead of the SI hardware; `tools/dolphin_srv.py` and
`tools/gcctl.py` drive it in Dolphin over the GDB stub (see their docstrings).

## Help

No support will be provided for this tool.

## Credits

- The SI polling and hot-plug handling, and the idea of lying to KPAD, come from
  [Barrel Blast Patch](https://github.com/quatric/Barrel-Blast-Patch) and
  [ACCF-Patch](https://github.com/quatric/ACCF-Patch).
- Wiimm: [wit / Wiimms ISO Tools](https://wit.wiimm.de/)

## License

Copyright (c) 2026 quatric
