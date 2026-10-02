# Reverse-engineering helpers

Small scripts used to find the hook sites in Kirby's Epic Yarn's `main.dol` (the game has no symbols):

- `disas.py <dol> <addr> <n>`: disassemble n instructions (needs `pip install capstone`)
- `callers.py <dol> <addr>`: every `bl` to a function
- `findref.py <dol> <addr>`: code that loads an address with `lis` + `addi`/load/store
- `match.py <ref dol> <target dol> <addr> <n>`: where a masked window of one DOL's code lies in another

They take a plain `sys/main.dol`.
