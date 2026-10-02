/* GameCube controller -> Wii Remote bridge for Kirby's Epic Yarn.
 *
 * The game links the SI library but not PAD, so nothing ever polls the pads:
 * gc_poll() drives the Serial Interface's own auto-polling (the approach is
 * Barrel Blast Patch's, hardware-tested there).  The pad's state is then fed
 * to the game through the Wii Remote library it already uses:
 *
 *   gc_poll    KPADiRead entry          turn the SI poller on for the channel
 *   gc_sample  KPADiRead sample check   queue a bare-Wii-Remote sample with the pad's buttons
 *   gc_probe   WPADProbe entry          report a Wii Remote while a pad is plugged in
 *   gc_post    KPADiRead return         write pointer (C-stick) and tilt into the returned status
 *
 * Epic Yarn is played with the Wii Remote held sideways, and the menus point at
 * the screen, so a bare remote with buttons, a pointer and tilt is all it needs.
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
    u8 shake;         /* parity of the fake shake */
    u32 prev_btn;     /* the buttons of the previous frame's sample */
    s32 px, py;       /* pointer, Q16, KPAD units */
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

#if defined(HOOK_SAMPLE) || defined(HOOK_POST)
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

/* Wii Remote buttons */
#define WM_LEFT  0x0001
#define WM_RIGHT 0x0002
#define WM_DOWN  0x0004
#define WM_UP    0x0008
#define WM_PLUS  0x0010
#define WM_2     0x0100
#define WM_1     0x0200
#define WM_B     0x0400
#define WM_A     0x0800
#define WM_MINUS 0x1000

#define STICK_ON 40       /* control stick: deflection that counts as a D-pad press */
#endif

#if defined(HOOK_SAMPLE)
static __attribute__((noinline)) u32 wm_buttons(u32 c, u32 h)
{
    u32 b = 0, d = 0;
    s32 x = (s32)((h >> 8) & 0xFF) - 128, y = (s32)(h & 0xFF) - 128;

    /* directions, as the player sees them on the screen */
    if ((h & GC_LEFT) || x < -STICK_ON) d |= 1;
    if ((h & GC_RIGHT) || x > STICK_ON) d |= 2;
    if ((h & GC_DOWN) || y < -STICK_ON) d |= 4;
    if ((h & GC_UP) || y > STICK_ON) d |= 8;
    if (*(volatile u8 *)(SIDEWAYS + c)) {
        /* the game turns a sideways remote's D-pad itself (raw Up is its Left, ...):
         * hand it the raw bits that come out right */
        if (d & 1) b |= WM_UP;
        if (d & 2) b |= WM_DOWN;
        if (d & 4) b |= WM_LEFT;
        if (d & 8) b |= WM_RIGHT;
    } else {
        if (d & 1) b |= WM_LEFT;
        if (d & 2) b |= WM_RIGHT;
        if (d & 4) b |= WM_DOWN;
        if (d & 8) b |= WM_UP;
    }

    if (h & (GC_A | GC_X)) b |= WM_2;       /* jump / confirm */
    if (h & (GC_B | GC_Y)) b |= WM_1;       /* yarn whip / cancel */
    if (h & GC_R) b |= WM_A;                /* pointer click; summon Angie in co-op */
    if (h & GC_L) b |= WM_MINUS;            /* controls */
    if (h & GC_START) b |= WM_PLUS;         /* pause */
    return b;
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
    u32 h, l, b, idx, cnt, size, i;

    if (c > 3)
        return;
    s = &ST->ch[c];
    if (!gc_in(c, &h, &l)) {
        s->seen = 0;
        s->ours = 0;
        return;
    }
    s->seen = 1;
    b = wm_buttons(c, h);
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
        *(u16 *)e = (u16)b;
        e[0x28] = 0;            /* no extension */
        e[0x29] = 0;            /* no error */
        e[0x40] = 2;            /* core buttons + accelerometer + pointer */
        k[0x17A] = (u8)(idx + 1);
        k[0x17B] = 1;
        s->ours = 1;
        s->prev_btn = b;
        return;
    }

    /* a real Wii Remote is delivering samples: the pad's buttons are added to them */
    s->ours = 0;
    if (cnt > size)
        cnt = size;
    for (i = 0; i < cnt; i++) {
        u32 j = idx + size - cnt + i;
        u8 *e = ring_entry(k, j % size);
        if (e[0x28] == 0)
            *(u16 *)e |= (u16)b;
    }
}
#endif

#if defined(HOOK_PROBE)
/* WPADProbe(chan, &type): report a Wii Remote while a pad is plugged in and no remote is */
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
        *type = 0;
    return 1;
}
#endif

#if defined(HOOK_POST)
/* 32-bit float with the bits of v / 65536 */
static __attribute__((noinline)) u32 q16f(s32 v)
{
    u32 sign = 0, m, e;
    if (v == 0)
        return 0;
    if (v < 0) {
        sign = 0x80000000u;
        v = -v;
    }
    m = (u32)v;
    e = 31 - __builtin_clz(m);                     /* highest set bit */
    m = (e >= 23) ? (m >> (e - 23)) : (m << (23 - e));
    return sign | ((e + 127 - 16) << 23) | (m & 0x7FFFFFu);
}

#define POINTER_MAX   0xF333        /* 0.95 */
#define POINTER_SPEED 2200          /* Q16 per frame at full deflection: ~0.034, a screen width in ~1 s */
#define TILT_MAX      0xB000        /* Q16: 0.7 g, about 45 degrees */
#define SHAKE_G       0x28000       /* Q16: 2.5 g, swung back and forth every frame */

static inline s32 cstick(u32 raw)
{
    s32 v = (s32)(raw & 0xFF) - 128;
    if (v > -12 && v < 12)
        return 0;
    return v > 0 ? v - 12 : v + 12;
}

/* KPADiRead, on its way out: buf = the KPADStatus array it returns, n = how many, c = the channel.
 * The pad has no pointer or accelerometer, so they are written into the status here. */
void gc_post(u8 *buf, s32 n, u32 c)
{
    struct chst *s;
    u32 h, l, i;
    s32 sx, sy, ax, ay, az;

    if (c > 3 || n <= 0 || n > 16)
        return;
    s = &ST->ch[c];
    if (!s->ours || !gc_in(c, &h, &l))
        return;

    sx = cstick(l >> 24);
    sy = cstick(l >> 16);
    s->px += sx * POINTER_SPEED / 116;
    s->py -= sy * POINTER_SPEED / 116;             /* stick up is screen up (KPAD's y grows downward) */
    if (s->px > POINTER_MAX) s->px = POINTER_MAX;  /* the game clamps to +-0.95 as well */
    if (s->px < -POINTER_MAX) s->px = -POINTER_MAX;
    if (s->py > POINTER_MAX) s->py = POINTER_MAX;
    if (s->py < -POINTER_MAX) s->py = -POINTER_MAX;

    /* tilt: the C-stick leans the remote.  Held sideways, the game reads the angle between the remote's
     * long axis and the floor (acc.y against acc.z) to aim the Tankbot and the Fire Engine */
    ax = sx * TILT_MAX / 116;
    ay = sy * TILT_MAX / 116;
    az = 0x10000 - (((ax * ax) >> 16) + ((ay * ay) >> 16)) / 2;
    if (h & GC_Z) {                                 /* shake: the co-op vehicles' boost */
        s->shake ^= 1;
        ax = s->shake ? SHAKE_G : -SHAKE_G;
    }

    for (i = 0; i < (u32)n; i++) {
        u32 *e = (u32 *)(buf + i * 0xF0);
        e[0x20 / 4] = q16f(s->px);                  /* pos */
        e[0x24 / 4] = q16f(s->py);
        e[0x28 / 4] = 0;                            /* vec */
        e[0x2C / 4] = 0;
        e[0x30 / 4] = 0;                            /* speed */
        ((u8 *)e)[0x5E] = 1;                        /* pointer valid */
        e[0x0C / 4] = q16f(ax);                     /* acc */
        e[0x10 / 4] = q16f(ay);
        e[0x14 / 4] = q16f(az);
        e[0x18 / 4] = 0x3F800000u;                  /* acc_value: 1 g */
        e[0x1C / 4] = 0;
    }
}
#endif
