SECTIONS
{
    . = BASE;
    .gctext : { *(.gctext) *(.text .text.*) *(.rodata .rodata.*) }
    . = ALIGN(32);
    .gcstate : { *(.gcstate) }
    /DISCARD/ : { *(.comment) *(.eh_frame) *(.note*) *(.bss) *(.sbss) *(.data .sdata) }
}
