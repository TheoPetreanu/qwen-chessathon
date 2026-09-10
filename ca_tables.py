"""Precomputed lookup tables for the bitboard engine.

Everything here is built once at import time and then referenced from
numba-jitted code as module globals, which numba freezes into the compiled
machine code as read-only constants.

Bitboard convention: bit i == square i, a1 = 0, h1 = 7, a8 = 56, h8 = 63.

Bitboards are uint64, NOT int64. This is not cosmetic. Magic lookups, the de
Bruijn bitscan and the SWAR popcount all rely on multiplication wrapping mod
2**64. On int64 that is signed overflow, which numba compiles to an LLVM `mul
nsw` -- undefined behaviour, and LLVM duly folds comparisons on the result to
garbage (observed: a value equal to 1 satisfying both `w >= 2` and `w == 1`).
On uint64 the wrap is defined and `>>` is a logical shift, so both problems
disappear.

Rule for every function below: bitboards and shift counts are uint64, array
indices and counters are int64, and the two never meet in one arithmetic
expression -- numba promotes uint64 mixed with int64 to float64.
"""
import numpy as np

MASK64 = (1 << 64) - 1

# --- piece indices -----------------------------------------------------------
WP, WN, WB, WR, WQ, WK, BP, BN, BB_, BR, BQ, BK = range(12)
NO_PIECE = 12
WHITE, BLACK = 0, 1

# --- file / rank masks -------------------------------------------------------
FILE_A = 0x0101010101010101
FILE_H = FILE_A << 7
RANK_1 = 0x00000000000000FF
RANK_8 = RANK_1 << 56

FILES = [FILE_A << i for i in range(8)]
RANKS = [RANK_1 << (8 * i) for i in range(8)]

ROOK_MAGICS = [
    0x1080009080400A20, 0x0A40021000200044, 0x20800A2002100080, 0x4280100008008084,
    0x0E00040200081020, 0x0280010200800400, 0x0080020000800100, 0x0200002040840112,
    0x0A00800090204000, 0x0800804000200080, 0x1000802000801008, 0x2028801001080080,
    0x0C10800400808800, 0x0842802400800200, 0x0216005804420001, 0x2554800041000080,
    0x8D10208000400080, 0x1253030020400082, 0x2020848010042000, 0x0200828008001000,
    0x0004808008000402, 0x9228808004000200, 0x0240040008020110, 0x00C0020001006084,
    0x1110800080204000, 0x04C0400140201000, 0x0420008080100020, 0x0004230100100209,
    0x2302080280040080, 0x2082020080040080, 0x1005000100040200, 0x820AD04200208104,
    0x0000400080800020, 0x880040A001401000, 0x0020801000802000, 0x0100801000800801,
    0x0001800402800800, 0x0160400408012010, 0x010810020400A821, 0x0922004682000914,
    0x0080004420024000, 0x0040008020008040, 0x2402002040820011, 0x1004201042020008,
    0x0004000800808004, 0x4004040002008080, 0x0000020001008080, 0x0520040880420009,
    0x0000522085020200, 0x0090400906208100, 0xB000100020068480, 0x0480100180080280,
    0x280C818400080080, 0x6000200440100801, 0x0000814810020400, 0x4010004104288600,
    0x0140120100204082, 0x030A001100402086, 0x1000208040081202, 0x0003001000200409,
    0x020200201014882A, 0x4081000400080203, 0x0000410810009204, 0x0000008402C11026,
]
ROOK_BITS = [12, 11, 11, 11, 11, 11, 11, 12, 11, 10, 10, 10, 10, 10, 10, 11, 11, 10, 10, 10, 10, 10, 10, 11, 11, 10, 10, 10, 10, 10, 10, 11, 11, 10, 10, 10, 10, 10, 10, 11, 11, 10, 10, 10, 10, 10, 10, 11, 11, 10, 10, 10, 10, 10, 10, 11, 12, 11, 11, 11, 11, 11, 11, 12]

BISHOP_MAGICS = [
    0x0040810202020022, 0x6020920AD3010004, 0x00100C1448400011, 0x0008208024522800,
    0x1004504000800C00, 0x10020904A1100602, 0x080900A820092000, 0x000922080C040200,
    0x000210D010010040, 0x2410611214210020, 0x08200418008102E0, 0x0008044042800080,
    0x80040D1040000001, 0x8000024820140000, 0x0386008424208480, 0x2A80210100900400,
    0x0004000890040800, 0x0420A0120C140080, 0x0090000104068010, 0x4084000A01220000,
    0x0000803400A04000, 0x0802001100620240, 0x4404018101015080, 0xC800808C40484800,
    0x0484046140082800, 0x1091600014080208, 0x000C020001080505, 0x0008080100220020,
    0x000A001022005002, 0x2480490042008209, 0x1090A20008921008, 0x00010141030400A0,
    0x940104910C202000, 0x8222420220101000, 0x8014009040020400, 0x0028020080080080,
    0x0008020010040900, 0x2230020200112580, 0x200204A608340218, 0x0008008020011100,
    0x0181019820004110, 0x104C00C410008460, 0x0002020201080204, 0x0083184200800800,
    0x0440020202000410, 0x2040208081008184, 0x0104080081200410, 0x0090024E00204241,
    0x0002015002100101, 0x1402088884100210, 0x0010262201102442, 0x4110000084040000,
    0x4004009022120080, 0x00202004A1020000, 0x0084099004008040, 0x8044480800408400,
    0xA008440209302200, 0x44200D0488010900, 0x1240410600443200, 0x8541900221084810,
    0x1000080908210100, 0x402000081001820A, 0x0040220805182484, 0x1402380808208021,
]
BISHOP_BITS = [6, 5, 5, 5, 5, 5, 5, 6, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 7, 7, 7, 7, 5, 5, 5, 5, 7, 9, 9, 7, 5, 5, 5, 5, 7, 9, 9, 7, 5, 5, 5, 5, 7, 7, 7, 7, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 6, 5, 5, 5, 5, 5, 5, 6]


# =============================================================================
# Table construction (plain Python, runs once at import)
# =============================================================================

def _sq(file, rank):
    return rank * 8 + file


def _ray_attacks(square, occ, deltas):
    """Sliding attacks from `square` over occupancy `occ`, stopping on blockers
    (the blocker square itself is included: it is a capture target)."""
    att = 0
    f0, r0 = square % 8, square // 8
    for df, dr in deltas:
        f, r = f0 + df, r0 + dr
        while 0 <= f < 8 and 0 <= r < 8:
            att |= 1 << _sq(f, r)
            if occ & (1 << _sq(f, r)):
                break
            f += df
            r += dr
    return att


ROOK_DELTAS = [(1, 0), (-1, 0), (0, 1), (0, -1)]
BISHOP_DELTAS = [(1, 1), (1, -1), (-1, 1), (-1, -1)]


def _relevant_mask(square, deltas):
    """Occupancy bits a magic index actually depends on: the rays minus their
    final square, because a blocker on the edge cannot shadow anything."""
    mask = 0
    f0, r0 = square % 8, square // 8
    for df, dr in deltas:
        f, r = f0 + df, r0 + dr
        while 0 <= f < 8 and 0 <= r < 8:
            nf, nr = f + df, r + dr
            if 0 <= nf < 8 and 0 <= nr < 8:
                mask |= 1 << _sq(f, r)
            f, r = nf, nr
    return mask


def _submasks(mask):
    bits = []
    m = mask
    while m:
        low = m & -m
        bits.append(low)
        m ^= low
    for i in range(1 << len(bits)):
        s = 0
        for j, b in enumerate(bits):
            if i & (1 << j):
                s |= b
        yield s


def _u64_array(values):
    return np.array([v & MASK64 for v in values], dtype=np.uint64)


# --- leaper attacks ----------------------------------------------------------
def _build_leapers():
    knight, king = [0] * 64, [0] * 64
    wpawn, bpawn = [0] * 64, [0] * 64
    for s in range(64):
        f, r = s % 8, s // 8
        for df, dr in ((1, 2), (2, 1), (2, -1), (1, -2),
                       (-1, -2), (-2, -1), (-2, 1), (-1, 2)):
            nf, nr = f + df, r + dr
            if 0 <= nf < 8 and 0 <= nr < 8:
                knight[s] |= 1 << _sq(nf, nr)
        for df in (-1, 0, 1):
            for dr in (-1, 0, 1):
                if df == 0 and dr == 0:
                    continue
                nf, nr = f + df, r + dr
                if 0 <= nf < 8 and 0 <= nr < 8:
                    king[s] |= 1 << _sq(nf, nr)
        for df in (-1, 1):
            nf = f + df
            if 0 <= nf < 8:
                if r + 1 < 8:
                    wpawn[s] |= 1 << _sq(nf, r + 1)
                if r - 1 >= 0:
                    bpawn[s] |= 1 << _sq(nf, r - 1)
    return knight, king, wpawn, bpawn


_knight, _king, _wpawn, _bpawn = _build_leapers()
KNIGHT_ATTACKS = _u64_array(_knight)
KING_ATTACKS = _u64_array(_king)
PAWN_ATTACKS = np.stack([_u64_array(_wpawn), _u64_array(_bpawn)])  # [colour][sq]


# --- magic sliding attacks ---------------------------------------------------
def _build_magic_table(magics, bits, deltas):
    """Flat attack table plus per-square (mask, magic, shift, offset)."""
    masks, offsets = [], []
    offset = 0
    for s in range(64):
        masks.append(_relevant_mask(s, deltas))
        offsets.append(offset)
        offset += 1 << bits[s]
    table = [0] * offset
    for s in range(64):
        shift = 64 - bits[s]
        for occ in _submasks(masks[s]):
            idx = ((occ * magics[s]) & MASK64) >> shift
            table[offsets[s] + idx] = _ray_attacks(s, occ, deltas)
    return _u64_array(table), _u64_array(masks), _u64_array(magics), \
        np.array(bits, dtype=np.int64), np.array(offsets, dtype=np.int64)


(ROOK_TABLE, ROOK_MASKS, ROOK_MAGIC, ROOK_BITCOUNT, ROOK_OFFSET) = \
    _build_magic_table(ROOK_MAGICS, ROOK_BITS, ROOK_DELTAS)
(BISHOP_TABLE, BISHOP_MASKS, BISHOP_MAGIC, BISHOP_BITCOUNT, BISHOP_OFFSET) = \
    _build_magic_table(BISHOP_MAGICS, BISHOP_BITS, BISHOP_DELTAS)

ROOK_SHIFT = np.array([64 - b for b in ROOK_BITS], dtype=np.int64)
BISHOP_SHIFT = np.array([64 - b for b in BISHOP_BITS], dtype=np.int64)
ROOK_IDXMASK = _u64_array([(1 << b) - 1 for b in ROOK_BITS])
BISHOP_IDXMASK = _u64_array([(1 << b) - 1 for b in BISHOP_BITS])
# shift counts must be uint64 so that `bb >> shift` stays a uint64 expression
ROOK_SHIFT = ROOK_SHIFT.astype(np.uint64)
BISHOP_SHIFT = BISHOP_SHIFT.astype(np.uint64)


# --- geometry: BETWEEN / LINE ------------------------------------------------
def _build_geometry():
    between = [[0] * 64 for _ in range(64)]
    line = [[0] * 64 for _ in range(64)]
    for a in range(64):
        for deltas in (ROOK_DELTAS, BISHOP_DELTAS):
            for df, dr in deltas:
                path = 0
                f, r = a % 8 + df, a // 8 + dr
                while 0 <= f < 8 and 0 <= r < 8:
                    b = _sq(f, r)
                    between[a][b] = path
                    path |= 1 << b
                    f += df
                    r += dr
            # full line through a and b, for both directions of each axis
            for df, dr in deltas:
                ray_fwd, ray_bwd = 0, 0
                f, r = a % 8 + df, a // 8 + dr
                while 0 <= f < 8 and 0 <= r < 8:
                    ray_fwd |= 1 << _sq(f, r)
                    f += df
                    r += dr
                f, r = a % 8 - df, a // 8 - dr
                while 0 <= f < 8 and 0 <= r < 8:
                    ray_bwd |= 1 << _sq(f, r)
                    f -= df
                    r -= dr
                whole = ray_fwd | ray_bwd | (1 << a)
                m = ray_fwd | ray_bwd
                while m:
                    low = m & -m
                    line[a][low.bit_length() - 1] = whole
                    m ^= low
    return between, line


_between, _line = _build_geometry()
BETWEEN = np.stack([_u64_array(row) for row in _between])
LINE = np.stack([_u64_array(row) for row in _line])


# --- zobrist hashing ---------------------------------------------------------
def _build_zobrist():
    import random
    rng = random.Random(0x5EED_C4E5)  # fixed seed: hashes reproduce exactly
    piece = [[rng.getrandbits(64) for _ in range(64)] for _ in range(12)]
    castling = [rng.getrandbits(64) for _ in range(16)]
    ep_file = [rng.getrandbits(64) for _ in range(8)]
    side = rng.getrandbits(64)
    return piece, castling, ep_file, side


_zp, _zc, _ze, _zs = _build_zobrist()
ZOBRIST_PIECE = np.stack([_u64_array(row) for row in _zp])
ZOBRIST_CASTLE = _u64_array(_zc)
ZOBRIST_EP = _u64_array(_ze)
ZOBRIST_SIDE = np.uint64(_zs & MASK64)

# --- castling rights bits ----------------------------------------------------
CR_WK, CR_WQ, CR_BK, CR_BQ = 1, 2, 4, 8

# Mask applied to castling rights whenever a piece leaves or lands on a square.
def _build_castle_mask():
    m = [15] * 64
    m[4] &= ~(CR_WK | CR_WQ)   # e1
    m[0] &= ~CR_WQ             # a1
    m[7] &= ~CR_WK             # h1
    m[60] &= ~(CR_BK | CR_BQ)  # e8
    m[56] &= ~CR_BQ            # a8
    m[63] &= ~CR_BK            # h8
    return np.array(m, dtype=np.int64)


CASTLE_MASK = _build_castle_mask()

DEBRUIJN = np.uint64(0x03F79D71B4CB0A89)
DEBRUIJN_INDEX = np.zeros(64, dtype=np.int64)
for _i in range(64):
    DEBRUIJN_INDEX[(((0x03F79D71B4CB0A89 << _i) & MASK64) >> 58)] = _i


# =============================================================================
# Evaluation masks
# =============================================================================
FILE_BB = _u64_array(FILES)
RANK_BB = _u64_array(RANKS)

ADJACENT_FILES = _u64_array([
    (FILES[f - 1] if f > 0 else 0) | (FILES[f + 1] if f < 7 else 0)
    for f in range(8)
])


def _build_spans():
    """FRONT_SPAN: squares strictly ahead on the same file.
    PASSED_MASK: the three-file box ahead that must be free of enemy pawns.
    """
    front = [[0] * 64 for _ in range(2)]
    passed = [[0] * 64 for _ in range(2)]
    for s in range(64):
        f, r = s % 8, s // 8
        for rr in range(r + 1, 8):
            front[0][s] |= 1 << _sq(f, rr)
        for rr in range(0, r):
            front[1][s] |= 1 << _sq(f, rr)
        for c in (0, 1):
            span = front[c][s]
            block = span
            for df in (-1, 1):
                nf = f + df
                if 0 <= nf < 8:
                    if c == 0:
                        for rr in range(r + 1, 8):
                            block |= 1 << _sq(nf, rr)
                    else:
                        for rr in range(0, r):
                            block |= 1 << _sq(nf, rr)
            passed[c][s] = block
    return front, passed


_front, _passed = _build_spans()
FRONT_SPAN = np.stack([_u64_array(_front[0]), _u64_array(_front[1])])
PASSED_MASK = np.stack([_u64_array(_passed[0]), _u64_array(_passed[1])])

# King zone: the king's own square, its 8 neighbours, and the three squares two
# ranks in front of it (where an attack usually builds).
def _build_king_zone():
    zone = [[0] * 64 for _ in range(2)]
    for s in range(64):
        f, r = s % 8, s // 8
        base = 1 << s
        for df in (-1, 0, 1):
            for dr in (-1, 0, 1):
                nf, nr = f + df, r + dr
                if 0 <= nf < 8 and 0 <= nr < 8:
                    base |= 1 << _sq(nf, nr)
        for c in (0, 1):
            z = base
            fr = r + 2 if c == 0 else r - 2
            if 0 <= fr < 8:
                for df in (-1, 0, 1):
                    nf = f + df
                    if 0 <= nf < 8:
                        z |= 1 << _sq(nf, fr)
            zone[c][s] = z
    return zone


_kz = _build_king_zone()
KING_ZONE = np.stack([_u64_array(_kz[0]), _u64_array(_kz[1])])

# Chebyshev distance between squares, used for king-proximity terms.
SQ_DISTANCE = np.zeros((64, 64), dtype=np.int64)
for _a in range(64):
    for _b in range(64):
        SQ_DISTANCE[_a][_b] = max(abs(_a % 8 - _b % 8), abs(_a // 8 - _b // 8))

CENTER_MANHATTAN = np.zeros(64, dtype=np.int64)
for _s in range(64):
    _f, _r = _s % 8, _s // 8
    CENTER_MANHATTAN[_s] = abs(2 * _f - 7) // 2 + abs(2 * _r - 7) // 2
