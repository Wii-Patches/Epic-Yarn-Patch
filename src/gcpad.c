/* GameCube controller -> Classic Controller bridge for Kirby's Epic Yarn.
 *
 * The game links the SI library but not PAD, so nothing ever polls the pads:
 * gc_poll() drives the Serial Interface's own auto-polling (the approach is
 * Barrel Blast Patch's, hardware-tested there).  gc_sample() turns the pad's
 * state into a Classic Controller sample in KPAD's ring, and gc_probe() makes
 * WPADProbe report a connected remote, so KPAD and Vague Rant and crediar's
 * Classic Controller Support (relocated to every region, see gcbuild.py) treat
 * the pad as one: the pad's left stick moves and points, its C-stick tilts.
 *
 * Addresses come in as -D macros, resolved per disc region by tools/anchors.py.
 */
typedef unsigned int u32;
typedef signed int s32;
typedef unsigned short u16;
typedef signed short s16;
typedef unsigned char u8;
typedef signed char s8;

#define R32(a) (*(volatile u32 *)(a))
#define SI_BASE   0xCD006400u
#define SI_OUT(c) (SI_BASE + (c) * 0xCu)
#define SI_INH(c) (SI_BASE + 4 + (c) * 0xCu)
#define SI_INL(c) (SI_BASE + 8 + (c) * 0xCu)
#define SI_POLL   (SI_BASE + 0x30u)
#define SI_COMCSR (SI_BASE + 0x34u)
#define SI_SR     (SI_BASE + 0x38u)

struct chst {
    u32 pad_;
    u8 norep;         /* consecutive frames with NOREP on this port */
    u8 ours;          /* the last sample queued for this channel was ours */
    u8 seen;          /* a pad answered on this frame */
    u8 pad0;
};
struct st {
    u32 feed[8];      /* DEBUG_FEED: pad responses (hi, lo) per channel, written by a debugger */
    u32 busy_tb;      /* when si:: was first seen busy (0 = idle) */
    u32 probe_tb;     /* last SIGetType, on any port */
    u32 rr;           /* the port whose turn it is to be probed */
    struct chst ch[4];
};
extern struct st gc_state;
#define ST (&gc_state)

static inline u32 tb(void)
{
    u32 t;
    __asm__ volatile("mftb %0" : "=r"(t));
    return t;
}

/* a valid, error-free pad response on this port */
static inline int gc_in(u32 c, u32 *h, u32 *l)
{
#ifdef DEBUG_FEED
    if (!ST->feed[c * 2])
        return 0;
    *h = ST->feed[c * 2];
    *l = ST->feed[c * 2 + 1];
    return 1;
#else
    u32 v = R32(SI_INH(c));
    if ((v & 0x80000000u) || !(v & 0x00800000u))
        return 0;
    *h = v;
    *l = R32(SI_INL(c));
    return 1;
#endif
}

#if defined(HOOK_POLL)
void gc_poll(u32 c)
{
    volatile u32 *types = (volatile u32 *)SI_TYPES;
    struct chst *s;
    u32 type, sisr, sh, poll, en, vb;
    int confirmed;
    s32 busy;

    if (c > 3)
        return;
    s = &ST->ch[c];
    sh = 24 - 8 * c;                  /* this port's byte in SISR */
    en = 0x80u >> c;                  /* SIPOLL: poll enable */
    vb = 0x08u >> c;                  /* SIPOLL: copy on vblank */

    /* probe a port until a standard pad answers, at most one probe every 0.25 s across all four ports and
     * taking turns: probing every frame collided with the pad's own polling on hardware */
    type = types[c];
    confirmed = !(type & 0x80) && (type & 0x18000000u) == 0x08000000u;
    if (c == ST->rr) {
        if (confirmed) {
            ST->rr = (c + 1) & 3;
        } else {
            u32 now = tb();
            if (now - ST->probe_tb >= 15187500u) {
                ST->probe_tb = now;
                ST->rr = (c + 1) & 3;
                ((u32 (*)(u32))FN_SIGETTYPE)(c);
            }
        }
    }

    /* an unplugged pad latches NOREP; si:: never reads it (no PAD library),
     * so copy a persistent one into the type cache ourselves, which makes
     * SIGetType probe the port again once a pad is plugged back in */
    sisr = R32(SI_SR);
    if (sisr & (0x08u << sh)) {
        if (s->norep < 10)
            s->norep++;
        else
            types[c] = 8;
    } else {
        s->norep = 0;
    }

    R32(SI_OUT(c)) = 0x00400300u;                                  /* poll command */
    R32(SI_SR) = (sisr & (0x0Fu << sh)) | (0x80u << sh);           /* ack this port's errors, latch OUT */

    type = types[c];
    confirmed = !(type & 0x80) && (type & 0x18000000u) == 0x08000000u;
    poll = R32(SI_POLL) & ~(en | vb);
    if (!(poll & 0xFF00u))
        poll |= 0x0100u;
    R32(SI_POLL) = poll | (confirmed ? (en | vb) : 0);
    /* si:: rewrites SIPOLL from its own shadow on every retrace */
    R32(SI_SHADOW) = (R32(SI_SHADOW) & ~(en | vb)) | (confirmed ? (en | vb) : 0);

    /* a pad unplugged mid-transfer leaves si::'s global busy flag wedged
     * (nothing times it out); force it idle after a second */
    busy = (s32)R32(SI_BUSY);
    if (busy == -1) {
        ST->busy_tb = 0;
    } else {
        u32 now = tb();
        if (ST->busy_tb == 0) {
            ST->busy_tb = now | 1;
        } else if (now - ST->busy_tb >= 60750000u) {
            u32 lvl = ((u32 (*)(void))FN_OSDISABLE)();
            R32(SI_BUSY) = (u32)-1;
            R32(SI_COMCSR) = 0x80000000u;
            ((void (*)(u32))FN_OSRESTORE)(lvl);
            ST->busy_tb = 0;
        }
    }
}
#endif

#if defined(HOOK_SAMPLE)
/* GameCube pad bits in the first response word */
#define GC_A     0x01000000u
#define GC_B     0x02000000u
#define GC_X     0x04000000u
#define GC_Y     0x08000000u
#define GC_START 0x10000000u
#define GC_Z     0x00100000u
#define GC_R     0x00200000u
#define GC_L     0x00400000u
#define GC_UP    0x00080000u
#define GC_DOWN  0x00040000u
#define GC_RIGHT 0x00020000u
#define GC_LEFT  0x00010000u

/* Classic Controller buttons as WPAD reports them */
#define CL_UP    0x0001
#define CL_LEFT  0x0002
#define CL_ZR    0x0004
#define CL_X     0x0008
#define CL_A     0x0010
#define CL_Y     0x0020
#define CL_B     0x0040
#define CL_ZL    0x0080
#define CL_R     0x0200
#define CL_PLUS  0x0400
#define CL_MINUS 0x1000
#define CL_L     0x2000
#define CL_DOWN  0x4000
#define CL_RIGHT 0x8000

static inline s16 stick(u32 raw)
{
    s32 v = ((s32)(raw & 0xFF) - 128) * 3;       /* pad ~+-100 -> game +-300 */
    if (v > 308)
        v = 308;
    if (v < -308)
        v = -308;
    return (s16)v;
}

/* The layout follows the Classic Controller mapping of the code the pad is paired with.
 *   B/A mode: A -> the remote's 2 (jump), B -> 1 (whip), X -> A, Y -> B
 *   Y/B mode: B -> 2, Y -> 1, A -> A, X -> B
 * so on the pad A always jumps and B always whips; X and Y are the remote's A and B.  L and R repeat jump and
 * whip, Z is -, Start is +. */
#ifdef LAYOUT_YB
#define CC_JUMP CL_B
#define CC_WHIP CL_Y
#define CC_WA   CL_A
#define CC_WB   CL_X
#else
#define CC_JUMP CL_A
#define CC_WHIP CL_B
#define CC_WA   CL_X
#define CC_WB   CL_Y
#endif

static __attribute__((noinline)) u32 cc_buttons(u32 h)
{
    u32 b = 0;

    if (h & GC_A) b |= CC_JUMP;
    if (h & GC_B) b |= CC_WHIP;
    if (h & GC_X) b |= CC_WA;
    if (h & GC_Y) b |= CC_WB;
    if (h & GC_START) b |= CL_PLUS;
    if (h & GC_Z) b |= CL_MINUS;
    if (h & GC_L) b |= CL_L;
    if (h & GC_R) b |= CL_R;
    if (h & GC_UP) b |= CL_UP;
    if (h & GC_DOWN) b |= CL_DOWN;
    if (h & GC_RIGHT) b |= CL_RIGHT;
    if (h & GC_LEFT) b |= CL_LEFT;
    return b;
}

/* a Classic Controller's data in a (zeroed) sample */
static __attribute__((noinline)) void fill_cc(u8 *e, u32 h, u32 l)
{
    *(u16 *)(e + 0x2A) = (u16)cc_buttons(h);
    *(s16 *)(e + 0x2C) = stick(h >> 8);          /* left stick x, y: the control stick */
    *(s16 *)(e + 0x2E) = stick(h);
    *(s16 *)(e + 0x30) = stick(l >> 24);         /* right stick x, y: the C-stick */
    *(s16 *)(e + 0x32) = stick(l >> 16);
    e[0x34] = (h & GC_L) ? 180 : 0;              /* analog L and R: the game reads them as buttons only */
    e[0x35] = (h & GC_R) ? 180 : 0;
    e[0x28] = 2;                                 /* extension: Classic Controller */
    e[0x29] = 0;                                 /* no extension error */
    e[0x40] = 8;                                 /* format: classic + accelerometer + pointer */
}

static inline u8 *ring_entry(u8 *k, u32 idx)
{
    if (idx < 0x10)
        return k + 0x180 + idx * 0x42;
    return *(u8 **)(k + 0x5A0) + (idx - 0x10) * 0x42;
}

/* KPADiRead, before its "any samples queued?" check: k = the channel's KPAD block, c = the channel */
void gc_sample(u8 *k, u32 c)
{
    struct chst *s;
    u32 h, l, idx, cnt, size, i;

    if (c > 3)
        return;
    s = &ST->ch[c];
    if (!gc_in(c, &h, &l)) {
        s->seen = 0;
        s->ours = 0;
        return;
    }
    s->seen = 1;
    size = 0x10 + *(u32 *)(k + 0x5A4);
    cnt = k[0x17B];
    idx = k[0x17A];
    if (idx >= size)
        idx = 0;

    if (cnt == 0) {
        /* nothing queued: no Wii Remote (device type 0xFD, or never seen), or our own sample showing through */
        u8 dev = k[0x5C];
        u8 *e;
        if (!(dev == 0 || dev == 0xFD || s->ours))
            return;
        e = ring_entry(k, idx);
        for (i = 0; i < 0x42; i += 2)
            *(u16 *)(e + i) = 0;
        fill_cc(e, h, l);
        k[0x17A] = (u8)(idx + 1);
        k[0x17B] = 1;
        s->ours = 1;
        return;
    }

    /* a real Wii Remote is delivering samples: a bare one gets the pad as its extension, a real Nunchuk or
     * Classic Controller is never touched */
    s->ours = 0;
    if (cnt > size)
        cnt = size;
    for (i = 0; i < cnt; i++) {
        u8 *e = ring_entry(k, (idx + size - cnt + i) % size);
        if (e[0x28] == 0)
            fill_cc(e, h, l);
    }
}
#endif

#if defined(HOOK_PROBE)
/* WPADProbe(chan, &type): report a Classic Controller on the channel while a pad is plugged in, unless the
 * channel already has a real remote */
u32 gc_probe(u32 c, u32 *type)
{
    u32 h, l;
    u8 *blk;
    s32 status;

    if (c > 3 || !gc_in(c, &h, &l))
        return 0;
    blk = *(u8 **)(WPAD_TBL + c * 4);
    status = *(s32 *)(blk + 0x900);
    if (status != -1 && blk[0x905] != 0xFD)
        return 0;
    if (type)
        *type = 2;
    return 1;
}
#endif
