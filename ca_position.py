"""Conversion between python-chess and the bitboard arrays.

python-chess is used only at the boundary: parsing the FEN we are handed and
turning our packed move back into a UCI string. It never appears in the search.
"""
import numpy as np
import chess

from ca_movegen import EMPTY, m_from, m_to, m_promo, compute_hash

MAX_PLY = 128
PROMO_CHARS = ['', 'n', 'b', 'r', 'q']


def new_position():
    bb = np.zeros(12, dtype=np.uint64)
    occ = np.zeros(3, dtype=np.uint64)
    mail = np.full(64, EMPTY, dtype=np.int8)
    st = np.zeros(5, dtype=np.int64)
    hsh = np.zeros(1, dtype=np.uint64)
    return bb, occ, mail, st, hsh


def new_stacks():
    undo = np.zeros((MAX_PLY + 8, 3), dtype=np.int64)
    undo_h = np.zeros(MAX_PLY + 8, dtype=np.uint64)
    moves = np.zeros((MAX_PLY + 8, 256), dtype=np.int32)
    return undo, undo_h, moves


def from_board(board, bb, occ, mail, st, hsh):
    """Fill the arrays from a python-chess Board."""
    bb[:] = 0
    occ[:] = 0
    mail[:] = EMPTY
    for sq, piece in board.piece_map().items():
        idx = (piece.piece_type - 1) + (0 if piece.color == chess.WHITE else 6)
        bb[idx] |= np.uint64(1) << np.uint64(sq)
        mail[sq] = idx
        occ[0 if piece.color == chess.WHITE else 1] |= np.uint64(1) << np.uint64(sq)
    occ[2] = occ[0] | occ[1]

    cr = 0
    if board.has_kingside_castling_rights(chess.WHITE):
        cr |= 1
    if board.has_queenside_castling_rights(chess.WHITE):
        cr |= 2
    if board.has_kingside_castling_rights(chess.BLACK):
        cr |= 4
    if board.has_queenside_castling_rights(chess.BLACK):
        cr |= 8

    st[0] = 0 if board.turn == chess.WHITE else 1
    st[1] = cr
    st[2] = board.ep_square if board.ep_square is not None else -1
    st[3] = board.halfmove_clock
    st[4] = board.fullmove_number
    hsh[0] = compute_hash(bb, st)


def from_fen(fen, bb, occ, mail, st, hsh):
    board = chess.Board(fen)
    from_board(board, bb, occ, mail, st, hsh)
    return board


def move_to_uci(m):
    frm, to, pr = m_from(int(m)), m_to(int(m)), m_promo(int(m))
    return chess.square_name(frm) + chess.square_name(to) + PROMO_CHARS[pr]
