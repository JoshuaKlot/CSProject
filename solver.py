"""
Minesweeper Solver
==================
Connects to the minesweeper game via TCP socket and uses constraint-based
logic to determine safe cells and mines.

Algorithm (Becerra, 2015 — "Algorithmic Approaches to Playing Minesweeper"):
  https://dash.harvard.edu/handle/1/14398552

  Phase 1 — Direct constraint resolution:
    a) For each revealed number N, build a constraint:
         (set_of_unrevealed_neighbours, N - flagged_neighbours)
    b) If remaining_count == 0            → all unrevealed neighbours are SAFE
    c) If remaining_count == |unrevealed| → all unrevealed neighbours are MINES

  Phase 2 — Iterative subset constraint reduction (Becerra §3.2):
    For every pair of constraints (A, count_A) and (B, count_B):
      If A ⊂ B:
        diff      = B \ A
        new_count = count_B − count_A
        • new_count == 0         → diff cells are all SAFE
        • new_count == |diff|    → diff cells are all MINES
        • 0 < new_count < |diff| → add (diff, new_count) as a new constraint
    Repeat until no new information can be derived.

  Phase 3 — Constraint-based probability (Becerra §3.3):
    When no deterministic move exists, estimate mine probability for each
    unrevealed border cell as the weighted average mine-fraction across all
    constraints that contain it:
        P(cell is mine) = mean( count_i / |cells_i|  for each constraint i
                                that contains cell )
    Cells not covered by any constraint are assigned the global background
    probability  total_mines_remaining / total_unrevealed.
    Click the cell with the lowest estimated probability.
"""

import socket
import json
import time
import random

HOST = 'localhost'
PORT = 5000
MOVE_DELAY = 0.3   # seconds between moves (slow enough to watch)


# ── Socket helpers ────────────────────────────────────────────────────────────

def connect():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    for attempt in range(20):
        try:
            s.connect((HOST, PORT))
            print("[Solver] Connected to game.")
            return s
        except ConnectionRefusedError:
            print(f"[Solver] Waiting for game... ({attempt+1})")
            time.sleep(1)
    raise RuntimeError("Could not connect to game after 20 attempts.")


def recv_state(sock, buf):
    """Read one newline-terminated JSON message."""
    while b"\n" not in buf:
        chunk = sock.recv(4096)
        if not chunk:
            raise ConnectionError("Game disconnected.")
        buf += chunk
    line, buf = buf.split(b"\n", 1)
    state = json.loads(line.decode())
    return state, buf


def send_move(sock, row, col, action="click"):
    msg = json.dumps({"row": row, "col": col, "action": action}) + "\n"
    sock.sendall(msg.encode())


# ── Solver logic ──────────────────────────────────────────────────────────────

def get_neighbours(r, c, rows, cols):
    result = []
    for dr in range(-1, 2):
        for dc in range(-1, 2):
            if dr == 0 and dc == 0:
                continue
            nr, nc = r + dr, c + dc
            if 0 <= nr < rows and 0 <= nc < cols:
                result.append((nr, nc))
    return result


def _propagate(constraints):
    """
    Phase 2: iterative subset-constraint reduction.

    Returns (safe_set, mine_set, reduced_constraints) where safe_set and
    mine_set contain newly derived certain cells, and reduced_constraints
    is the updated list after incorporating that knowledge.

    Algorithm: Becerra (2015) §3.2 — for every ordered pair (A, B) where
    A ⊂ B, derive B \ A with count count_B − count_A.
    """
    safe  = set()
    mines = set()

    changed = True
    while changed:
        changed = False

        # --- direct resolution pass ---
        surviving = []
        for cells, count in constraints:
            if count == 0:
                newly_safe = cells - safe - mines
                if newly_safe:
                    safe.update(newly_safe)
                    changed = True
            elif count == len(cells):
                newly_mined = cells - safe - mines
                if newly_mined:
                    mines.update(newly_mined)
                    changed = True
            else:
                surviving.append((cells, count))
        constraints = surviving

        # --- subset-reduction pass ---
        new_constraints = []
        for i, (cells_a, count_a) in enumerate(constraints):
            for j, (cells_b, count_b) in enumerate(constraints):
                if i >= j:
                    continue
                # Check both A⊂B and B⊂A
                for (small_cells, small_count), (big_cells, big_count) in [
                    ((cells_a, count_a), (cells_b, count_b)),
                    ((cells_b, count_b), (cells_a, count_a)),
                ]:
                    if small_cells < big_cells:          # strict subset
                        diff      = big_cells - small_cells
                        new_count = big_count - small_count
                        if new_count < 0 or new_count > len(diff):
                            continue                     # inconsistent, skip
                        candidate = (frozenset(diff), new_count)
                        if (candidate not in constraints and
                                candidate not in new_constraints):
                            new_constraints.append(candidate)
                            changed = True

        constraints = constraints + new_constraints

        # --- strip now-known cells from remaining constraints ---
        updated = []
        for cells, count in constraints:
            unknown = cells - safe - mines
            if not unknown:
                continue
            new_count = count - len(cells & mines)
            if new_count < 0 or new_count > len(unknown):
                continue                                 # inconsistent, skip
            updated.append((frozenset(unknown), new_count))
        constraints = updated

    return safe, mines, constraints


def solve_step(board):
    """
    Phase 1 + 2: build constraints from the board, then propagate.

    Returns:
        moves        – list of (row, col, action) with deterministic moves
        constraints  – remaining unresolved constraints (for Phase 3)
    """
    rows = len(board)
    cols = len(board[0])

    constraints = []

    # Phase 1 — build one constraint per numbered cell
    for r in range(rows):
        for c in range(cols):
            cell = board[r][c]
            if not cell.isdigit():
                continue

            number       = int(cell)
            neighbours   = get_neighbours(r, c, rows, cols)
            unrevealed   = set()
            flagged_count = 0

            for nr, nc in neighbours:
                nb = board[nr][nc]
                if nb == 'E':
                    unrevealed.add((nr, nc))
                elif nb == 'F':
                    flagged_count += 1

            remaining = number - flagged_count
            if remaining < 0:
                continue    # over-flagged (shouldn't happen in a clean game)
            if not unrevealed:
                continue    # fully resolved cell, nothing to add

            constraints.append((frozenset(unrevealed), remaining))

    # Phase 2 — propagate subset constraints
    safe, mines, constraints = _propagate(constraints)

    # Build move list
    moves = []
    for (r, c) in sorted(mines):
        if board[r][c] == 'E':
            moves.append((r, c, 'flag'))
    for (r, c) in sorted(safe):
        if board[r][c] == 'E':
            moves.append((r, c, 'click'))

    return moves, constraints, mines


def choose_probabilistic_move(board, constraints, total_mines, known_mines=None):
    """
    Phase 3: pick the safest unrevealed cell via mine-probability estimate.

    For border cells (those appearing in at least one constraint):
        P(mine) = mean of (count_i / |cells_i|) over all constraints i
                  that contain the cell.

    For interior cells (not constrained at all):
        P(mine) = remaining_mines / total_unconstrained_cells

    known_mines: set of (r,c) cells that solve_step already determined are
                 mines this turn — they are queued to be flagged but still
                 show as 'E' on the board, so we must exclude them manually.

    Source: Becerra (2015) §3.3
    """
    rows = len(board)
    cols = len(board[0])
    known_mines = known_mines or set()

    # Exclude cells already known to be mines (queued for flagging but board
    # not yet updated) — this was the source of "clicking a mine" bugs.
    unrevealed = [
        (r, c)
        for r in range(rows) for c in range(cols)
        if board[r][c] == 'E' and (r, c) not in known_mines
    ]
    if not unrevealed:
        return None

    flagged_count = sum(1 for r in range(rows) for c in range(cols)
                        if board[r][c] == 'F')
    # Also count the queued-but-not-yet-flagged mines
    mines_remaining = max(total_mines - flagged_count - len(known_mines), 0)

    # Cells that appear in at least one constraint
    constrained_cells = set()
    for cells, _ in constraints:
        constrained_cells.update(cells)
    # Don't consider known mines as candidates even if still in a constraint
    constrained_cells -= known_mines

    unconstrained = [pos for pos in unrevealed if pos not in constrained_cells]

    # Background probability for unconstrained interior cells.
    # Denominator is unconstrained count, not total unrevealed — border cells
    # already have their own estimate, so we only spread remaining mines over
    # the truly unconstrained region.
    if unconstrained:
        background_prob = min(mines_remaining / len(unconstrained), 1.0)
    else:
        background_prob = 1.0   # no unconstrained fallback available

    risk = {}
    for pos in unrevealed:
        if pos in constrained_cells:
            fractions = [count / len(cells)
                         for cells, count in constraints
                         if pos in cells]
            risk[pos] = sum(fractions) / len(fractions)
        else:
            risk[pos] = background_prob

    min_risk = min(risk.values())
    candidates = [pos for pos, p in risk.items() if p == min_risk]
    r, c = random.choice(candidates)
    print(f"[Solver] Probabilistic guess: ({r},{c})  estimated P(mine)={min_risk:.3f}")
    return (r, c, 'click')


def first_move(board):
    """Start from the centre — statistically the safest opening (fewest edge/corner effects)."""
    rows = len(board)
    cols = len(board[0])
    candidates = [
        (rows // 2, cols // 2),
        (0, 0),
        (0, cols - 1),
        (rows - 1, 0),
        (rows - 1, cols - 1),
    ]
    for (r, c) in candidates:
        if board[r][c] == 'E':
            return (r, c, 'click')
    return (0, 0, 'click')


def is_all_unrevealed(board):
    return all(board[r][c] == 'E'
               for r in range(len(board))
               for c in range(len(board[0])))


# ── Main loop ─────────────────────────────────────────────────────────────────

def main():
    sock       = connect()
    buf        = b""
    move_queue = []

    print("[Solver] Waiting for game state...")

    while True:
        try:
            state, buf = recv_state(sock, buf)
        except ConnectionError:
            print("[Solver] Game disconnected.")
            break

        board     = state["board"]
        game_over = state.get("game_over", False)
        won       = state.get("won", False)
        # total mines may be sent by the server; fall back to a sensible default
        total_mines = state.get("mines", 40)

        if game_over:
            if won:
                print("[Solver] Game WON!")
            else:
                print("[Solver] Game Lost — hit a mine.")
            print("[Solver] Waiting for new game...")
            move_queue.clear()
            continue

        # Print board
        print("\n[Solver] Board state:")
        for r, row in enumerate(board):
            print(f"  {r:2d}: {' '.join(c if c not in ('E', 'F') else ('.' if c == 'E' else 'F') for c in row)}")

        # Compute moves when the queue is empty
        if not move_queue:
            if is_all_unrevealed(board):
                print("[Solver] First move — picking centre cell.")
                move = first_move(board)
                move_queue.append(move)
            else:
                moves, constraints, known_mines = solve_step(board)
                if moves:
                    print(f"[Solver] {len(moves)} deterministic move(s) found.")
                    move_queue.extend(moves)
                else:
                    print("[Solver] No deterministic move — using probabilistic Phase 3.")
                    move = choose_probabilistic_move(
                        board, constraints, total_mines, known_mines
                    )
                    if move:
                        move_queue.append(move)
                    else:
                        print("[Solver] No moves available — board complete?")

        # Send one move per received state
        if move_queue:
            r, c, action = move_queue.pop(0)
            print(f"[Solver] {action.upper()} → ({r}, {c})"
                  f"  ({len(move_queue)} more queued)")
            send_move(sock, r, c, action)
            time.sleep(MOVE_DELAY)


if __name__ == "__main__":
    main()