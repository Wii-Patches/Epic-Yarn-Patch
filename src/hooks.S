/* Entry stubs: save every volatile register, call the C hook, restore, run the
 * instruction the hook replaced, and branch back to just after it.  The *_RET
 * addresses (hook site + 4) come in as -D macros. */
    .macro SAVE
    stwu    1, -0x70(1)
    stw     0, 0x0c(1)
    stw     3, 0x10(1)
    stw     4, 0x14(1)
    stw     5, 0x18(1)
    stw     6, 0x1c(1)
    stw     7, 0x20(1)
    stw     8, 0x24(1)
    stw     9, 0x28(1)
    stw     10, 0x2c(1)
    stw     11, 0x30(1)
    stw     12, 0x34(1)
    mflr    0
    stw     0, 0x38(1)
    mfcr    0
    stw     0, 0x3c(1)
    mfctr   0
    stw     0, 0x40(1)
    mfxer   0
    stw     0, 0x44(1)
    .endm

    .macro RESTORE_ALL          /* everything but r0 */
    lwz     0, 0x44(1)
    mtxer   0
    lwz     0, 0x40(1)
    mtctr   0
    lwz     0, 0x3c(1)
    mtcr    0
    lwz     0, 0x38(1)
    mtlr    0
    lwz     3, 0x10(1)
    lwz     4, 0x14(1)
    lwz     5, 0x18(1)
    lwz     6, 0x1c(1)
    lwz     7, 0x20(1)
    lwz     8, 0x24(1)
    lwz     9, 0x28(1)
    lwz     10, 0x2c(1)
    lwz     11, 0x30(1)
    lwz     12, 0x34(1)
    .endm

    .section .gctext, "ax"
    .globl hook_poll, hook_sample, hook_probe

# KPADiRead(chan, buf, n, err, flag) entry: r3 = channel
hook_poll:
    SAVE
    bl      gc_poll
    RESTORE_ALL
    lwz     0, 0x0c(1)
    addi    1, 1, 0x70
    stwu    1, -0x240(1)        # original instruction
    b       POLL_RET

# KPADiRead before the sample-count check: r21 = the channel's KPAD block, r25 = channel
hook_sample:
    SAVE
    mr      3, 21
    mr      4, 25
    bl      gc_sample
    RESTORE_ALL
    lwz     0, 0x0c(1)
    addi    1, 1, 0x70
    lbz     0, 0x17b(21)        # original instruction
    b       SAMPLE_RET

# WPADProbe(chan, &type) entry
hook_probe:
    SAVE
    bl      gc_probe
    stw     3, 0x08(1)
    RESTORE_ALL
    lwz     0, 0x08(1)
    addi    1, 1, 0x70
    cmpwi   0, 0
    beq     1f
    li      3, 0                # a (virtual) Wii Remote is connected
    blr
1:  stwu    1, -0x10(1)         # original instruction
    b       PROBE_RET


    .section .gcstate, "aw", @progbits
    .globl gc_state
    .balign 32
gc_state:
    .space  0x100
