"""Generate magic-bitboard constants for rooks and bishops.

Run once offline; the resulting numbers are pasted into ca_tables.py so the
agent never has to search for magics at init time.
"""
import random

M64 = (1 << 64) - 1

def sq(f, r):
    return r * 8 + f

def slider_attacks(square, occ, deltas):
    """Attacks from `square` given occupancy `occ`, walking each (df, dr)."""
    att = 0
    f0, r0 = square % 8, square // 8
    for df, dr in deltas:
        f, r = f0 + df, r0 + dr
        while 0 <= f < 8 and 0 <= r < 8:
            att |= 1 << sq(f, r)
            if occ & (1 << sq(f, r)):
                break
            f += df
            r += dr
    return att

ROOK_DELTAS = [(1, 0), (-1, 0), (0, 1), (0, -1)]
BISHOP_DELTAS = [(1, 1), (1, -1), (-1, 1), (-1, -1)]

def relevant_mask(square, deltas):
    """Occupancy bits that matter: the ray, minus the edge square of each ray."""
    mask = 0
    f0, r0 = square % 8, square // 8
    for df, dr in deltas:
        f, r = f0 + df, r0 + dr
        while 0 <= f < 8 and 0 <= r < 8:
            nf, nr = f + df, r + dr
            if 0 <= nf < 8 and 0 <= nr < 8:
                mask |= 1 << sq(f, r)
            f, r = nf, nr
    return mask

def subsets(mask):
    """Every submask of `mask`, via the standard carry-rippling trick."""
    bits = []
    m = mask
    while m:
        lsb = m & -m
        bits.append(lsb)
        m ^= lsb
    n = len(bits)
    for i in range(1 << n):
        s = 0
        for j in range(n):
            if i & (1 << j):
                s |= bits[j]
        yield s

def find_magic(square, deltas, rng):
    mask = relevant_mask(square, deltas)
    bits = bin(mask).count("1")
    size = 1 << bits
    occs, atts = [], []
    for occ in subsets(mask):
        occs.append(occ)
        atts.append(slider_attacks(square, occ, deltas))
    shift = 64 - bits
    for _ in range(10_000_000):
        # Sparse candidates (AND of three randoms) hit far more often.
        magic = rng.getrandbits(64) & rng.getrandbits(64) & rng.getrandbits(64)
        # Cheap reject: the top byte of mask*magic should be well populated.
        if bin((mask * magic) & 0xFF00000000000000).count("1") < 6:
            continue
        table = [None] * size
        ok = True
        for occ, att in zip(occs, atts):
            idx = ((occ * magic) & M64) >> shift
            if table[idx] is None:
                table[idx] = att
            elif table[idx] != att:
                ok = False
                break
        if ok:
            return magic, bits
    raise RuntimeError("no magic found for square %d" % square)

def main():
    rng = random.Random(0xC0FFEE)  # fixed seed -> reproducible constants
    for name, deltas in (("ROOK", ROOK_DELTAS), ("BISHOP", BISHOP_DELTAS)):
        magics, bitcounts = [], []
        for s in range(64):
            m, b = find_magic(s, deltas, rng)
            magics.append(m)
            bitcounts.append(b)
        print("%s_MAGICS = [" % name)
        for i in range(0, 64, 4):
            print("    " + ", ".join("0x%016X" % m for m in magics[i:i + 4]) + ",")
        print("]")
        print("%s_BITS = %r" % (name, bitcounts))
        print()

if __name__ == "__main__":
    main()
