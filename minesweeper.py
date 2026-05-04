import tkinter as tk
import random
from tkinter import messagebox
import sys
import socket
import json
import threading
 
host = 'localhost'
port = 5000
global rows, columns
rows=10
columns=10
# Global socket reference
client_socket = None
server_socket = None
 
def start_server():
    """Start socket server in background thread, accept one client."""
    global client_socket, server_socket
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind(('', port))
    server_socket.listen(1)
    print(f"[Game] Waiting for solver to connect on port {port}...")
    try:
        client_socket, addr = server_socket.accept()
        client_socket.setblocking(False)
        print(f"[Game] Solver connected from {addr}")
    except Exception as e:
        print(f"[Game] Socket error: {e}")
 
def send_state(board, actual_board, game_over=False, won=False, total_mines=0):
    """Send current visible board state to solver."""
    global client_socket
    if client_socket is None:
        return
    try:
        state = {
            "board": board,
            "rows": len(board),
            "cols": len(board[0]),
            "game_over": game_over,
            "won": won,
            "total_mines": total_mines,
        }
        data = json.dumps(state) + "\n"
        client_socket.sendall(data.encode())
    except Exception:
        pass
 
def recv_move():
    """Non-blocking receive of a move from solver. Returns (row, col) or None."""
    global client_socket
    if client_socket is None:
        return None
    try:
        data = b""
        while True:
            chunk = client_socket.recv(1024)
            if not chunk:
                break
            data += chunk
            if b"\n" in data:
                break
        if data:
            move = json.loads(data.decode().strip())
            return move.get("row"), move.get("col"), move.get("action", "click")
    except BlockingIOError:
        return None
    except Exception:
        return None
 
 
def generateRandomBoard(rows, col, mineCount=None, safeRow=None, safeCol=None):
    """Generate a board with exactly mineCount mines, avoiding the safe zone on first click."""
    total_cells = rows * col
 
    # Build safe cells set (3x3 around first click)
    safe_cells = set()
    if safeRow is not None and safeCol is not None:
        for drow in range(-1, 2):
            for dcol in range(-1, 2):
                nr, nc = safeRow + drow, safeCol + dcol
                if 0 <= nr < rows and 0 <= nc < col:
                    safe_cells.add((nr, nc))
 
    # If mineCount not provided, fall back to ~1-in-6 random placement
    if mineCount is None:
        board = [[] for _ in range(rows)]
        actual_mine_count = 0
        for i in range(rows):
            for j in range(col):
                if (i, j) in safe_cells:
                    ranchar = "E"
                else:
                    ranchar = random.choice(["E", "E", "E", "E", "E", "M"])
                if ranchar == "M":
                    actual_mine_count += 1
                board[i].append(ranchar)
        return [board, actual_mine_count]
 
    # Exact mine placement
    # Candidate cells exclude the safe zone
    all_cells = [(r, c) for r in range(rows) for c in range(col)]
    candidates = [cell for cell in all_cells if cell not in safe_cells]
 
    # Cap mine count so it fits
    max_mines = len(candidates)
    mineCount = min(mineCount, max_mines)
 
    mine_set = set(random.sample(candidates, mineCount))
 
    board = [[] for _ in range(rows)]
    for i in range(rows):
        for j in range(col):
            board[i].append("M" if (i, j) in mine_set else "E")
 
    return [board, mineCount]
 
 
def numberMineBoard(board):
    vis = [["0" for _ in range(len(board[0]))] for _ in range(len(board))]
    numberOfRows = len(board)
    numberOfColumns = len(board[0])
    for i in range(numberOfRows):
        for j in range(numberOfColumns):
            if board[i][j] == "M":
                vis[i][j] = "M"
                for drow in range(-1, 2):
                    for dcol in range(-1, 2):
                        nrow = i + drow
                        ncol = j + dcol
                        if 0 <= nrow < numberOfRows and 0 <= ncol < numberOfColumns:
                            if board[nrow][ncol] == "M":
                                continue
                            vis[nrow][ncol] = str(int(vis[nrow][ncol]) + 1)
    return vis
 
 
def dfs(row, col, board, actualBoard, vis, buttons):
    vis[row][col] = 1
    board[row][col] = "B"
    buttons.add(len(board[0]) * row + col)
    for drow in range(-1, 2):
        for dcol in range(-1, 2):
            nrow = row + drow
            ncol = col + dcol
            if (0 <= nrow < len(board) and 0 <= ncol < len(board[0])
                    and not vis[nrow][ncol]):
                if actualBoard[nrow][ncol] == "0":
                    dfs(nrow, ncol, board, actualBoard, vis, buttons)
                else:
                    board[nrow][ncol] = actualBoard[nrow][ncol]
                    buttons.add(len(board[0]) * nrow + ncol)
 
 
def checkSpaces(mineCount, board, actualBoard, buttons):
    cnt = sum(board[i][j] == 'E'
              for i in range(len(board))
              for j in range(len(board[0])))
    if cnt == mineCount:
        for i in range(len(board)):
            for j in range(len(board[0])):
                val = i * len(board[0]) + j
                if actualBoard[i][j] == 'M':
                    buttons[val].config(text="", bg="#76EEC6",
                                        state=tk.DISABLED, borderwidth=1)
        return True
    return False
 
 
def markMinesAtEnd(board, actualBoard, buttons, disabledbuttons):
    for i in range(len(board)):
        for j in range(len(board[0])):
            val = i * len(board[0]) + j
            if actualBoard[i][j] == 'M':
                color = "#E3CF57" if val in disabledbuttons else "red"
                if val in disabledbuttons:
                    disabledbuttons.remove(val)
                buttons[val].config(text=actualBoard[i][j], bg=color,
                                    state=tk.DISABLED, borderwidth=1)
    for i in disabledbuttons:
        buttons[i].config(text="X", bg="#C1CDCD",
                          state=tk.DISABLED, borderwidth=1)
 
 
def playerClicks(crow, ccol, board, actualBoard, vis, mineCount,
                 buttons, buttonsClear, disabledbuttons):
    if actualBoard[crow][ccol] == "M":
        markMinesAtEnd(board, actualBoard, buttons, disabledbuttons)
        return "Lost"
    elif actualBoard[crow][ccol] != "0":
        board[crow][ccol] = actualBoard[crow][ccol]
    else:
        dfs(crow, ccol, board, actualBoard, vis, buttonsClear)
    if checkSpaces(mineCount, board, actualBoard, buttons):
        return "Win"
    return "Cont"
 
 
def create_board(board, actualBoard, coordinates, vis, buttonsclear,
                 mineCount, dimensions, rawBoard, userMineCount=None):
    n = len(board)
    m = len(board[0])
    dimOfRow = dimensions[0][0]
    dimOfCol = dimensions[0][1]
    disabledbuttons = []
 
    state = {"firstClick": True, "rawBoard": rawBoard,
             "actualBoard": actualBoard, "mineCount": mineCount}
 
    def close():
        print("Closing, Thanks for Playing!")
        root.destroy()
        sys.exit()
 
    def restart():
        root.destroy()
        details = generateRandomBoard(dimOfRow, dimOfCol, userMineCount)
        newboard = details[0]
        newmineCount = details[1]
        create_board(makeGameboard(newboard), numberMineBoard(newboard),
                     makeCoordinates(newboard), makeVisited(newboard),
                     set(), newmineCount, dimensions, newboard, userMineCount)
 
    def get_visible_board():
        """Build the visible board state for sending to solver."""
        visible = []
        for i in range(n):
            row = []
            for j in range(m):
                idx = i * m + j
                if idx in disabledbuttons:
                    row.append("F")
                elif board[i][j] == "E":
                    row.append("E")
                elif board[i][j] == "B":
                    row.append("0")
                else:
                    row.append(board[i][j])
            visible.append(row)
        return visible
 
    def apply_solver_move():
        """Check for a move from solver and apply it."""
        result = recv_move()
        if result and result[0] is not None:
            row, col, action = result
            value = row * m + col
            if action == "flag":
                handle_right_click(value, buttons)
            else:
                handle_left_click(value, buttons)
        root.after(200, apply_solver_move)
 
    def handle_left_click(value, buttons):
        if value == -1:
            restart()
            return
 
        button = buttons[value]
        row = coordinates[value][0]
        col = coordinates[value][1]
 
        if value in disabledbuttons:
            return
 
        if state["firstClick"]:
            state["firstClick"] = False
            details = generateRandomBoard(dimOfRow, dimOfCol, userMineCount, row, col)
            state["rawBoard"] = details[0]
            state["mineCount"] = details[1]
            state["actualBoard"] = numberMineBoard(state["rawBoard"])
            for i in range(n):
                for j in range(m):
                    board[i][j] = makeGameboard(state["rawBoard"])[i][j]
                    actualBoard[i][j] = state["actualBoard"][i][j]
            mineCount_ref[0] = state["mineCount"]
 
        current_mine_count = mineCount_ref[0]
        result = playerClicks(row, col, board, actualBoard, vis,
                              current_mine_count, buttons, buttonsclear,
                              disabledbuttons)
 
        if result == "Lost":
            send_state(get_visible_board(), actualBoard, game_over=True, won=False,
                       total_mines=mineCount_ref[0])
            response = messagebox.askyesno(
                "Game Over", " You Lost\n Do you want to replay?", icon='warning')
            if response:
                restart()
            else:
                close()
        elif result == "Win":
            buttonlabel = actualBoard[row][col]
            button.config(text=buttonlabel, bg="lightblue",
                          state=tk.DISABLED, borderwidth=1)
            send_state(get_visible_board(), actualBoard, game_over=True, won=True,
                       total_mines=mineCount_ref[0])
            response = messagebox.askyesno(
                "You Won!", " You Cleared all the mines\n Do you want to replay?",
                icon='info')
            if response:
                restart()
            else:
                close()
        else:
            buttonlabel = actualBoard[row][col]
            button.config(text=buttonlabel, bg="lightblue",
                          state=tk.DISABLED, borderwidth=1)
            for button_index in buttonsclear:
                label_text = actualBoard[coordinates[button_index][0]][
                    coordinates[button_index][1]]
                if label_text == "0":
                    label_text = " "
                buttons[button_index].config(text=label_text, bg="lightblue",
                                             state=tk.DISABLED, borderwidth=1)
            buttonsclear.clear()
            send_state(get_visible_board(), actualBoard, total_mines=mineCount_ref[0])
 
    def handle_right_click(value, buttons):
        button = buttons[value]
        if value not in disabledbuttons:
            button.config(text='F', fg="red", borderwidth=1)
            disabledbuttons.append(value)
        else:
            button.config(text=" ", fg="red", borderwidth=1)
            disabledbuttons.remove(value)
        send_state(get_visible_board(), actualBoard, total_mines=mineCount_ref[0])
 
    def closeExisting():
        root.destroy()
        backToMainMenu()
 
    mineCount_ref = [mineCount]
 
    root = tk.Tk()
    root.title("Minesweeper")
 
    # Mine counter label at top
    mine_label = tk.Label(root, text=f"Mines: {mineCount_ref[0]}", font=("calibre", 10, "bold"))
    mine_label.grid(row=0, column=0, columnspan=m)
 
    buttons = []
    colors = ["#F0FFFF", "#C1CDCD"]
    start = 0
    for i in range(n):
        for j in range(m):
            value = i * m + j
            cbg = colors[start]
            button = tk.Button(root, text=" ", width=4, height=2,
                               borderwidth=1, bg=cbg)
            button.bind("<Button-1>",
                        lambda event, v=value: handle_left_click(v, buttons))
            button.bind("<Button-3>",
                        lambda event, v=value: handle_right_click(v, buttons))
            buttons.append(button)
            button.grid(row=i + 1, column=j, padx=0, pady=0)
            start = not start
        if m % 2 == 0:
            colors = colors[::-1]
 
    new_board_button = tk.Button(root, text="New Board")
    new_board_button.bind("<Button-1>",
                          lambda event: handle_left_click(-1, buttons))
    new_board_button.grid(row=n + 1, columnspan=m + 1, padx=10, pady=10)
 
    additional_button = tk.Button(root, text="Main Menu",
                                  command=lambda: closeExisting())
    additional_button.grid(row=n + 3, column=0, columnspan=m,
                           padx=10, pady=5)
 
    root.protocol("WM_DELETE_WINDOW", close)
 
    root.after(500, apply_solver_move)
    send_state(get_visible_board(), actualBoard, total_mines=mineCount_ref[0])
 
    root.mainloop()
 
 
def makeCoordinates(board):
    coords = {}
    for i in range(len(board)):
        for j in range(len(board[0])):
            coords[i * len(board[0]) + j] = (i, j)
    return coords
 
 
def makeVisited(board):
    return [[0] * len(board[0]) for _ in range(len(board))]
 
 
def makeGameboard(board):
    return [['E'] * len(board[0]) for _ in range(len(board))]
 
 
def backToMainMenu():
    dimensions = []
 
    def left_click():
        rows_str = row_val.get()
        cols_str = col_val.get()
        mines_str = mine_val.get()
 
        if not rows_str.isdigit() or not cols_str.isdigit():
            messagebox.showerror("Invalid Input", "Please enter valid integers for rows and columns.")
            return
 
        r, c = int(rows_str), int(cols_str)
 
        # Validate mine count
        user_mines = None
        if mines_str.strip() != "":
            if not mines_str.isdigit():
                messagebox.showerror("Invalid Input", "Please enter a valid integer for mines.")
                return
            user_mines = int(mines_str)
            max_possible = r * c - 1  # at least one safe cell
            if user_mines < 1:
                messagebox.showerror("Invalid Input", "Mine count must be at least 1.")
                return
            if user_mines >= r * c:
                messagebox.showerror("Invalid Input",
                    f"Mine count must be less than the total number of cells ({r * c}).")
                return
 
        dimensions.append((r, c))
        root.destroy()
 
        placeholder = [['E'] * c for _ in range(r)]
        blank_actual = [['0'] * c for _ in range(r)]
 
        create_board(makeGameboard(placeholder), blank_actual,
                     makeCoordinates(placeholder), makeVisited(placeholder),
                     set(), 0, dimensions, placeholder, user_mines)
 
    def on_closing():
        root.destroy()
        sys.exit()
 
    root = tk.Tk()
    root.title("Minesweeper")
 
    window_width, window_height = 420, 240
    root.geometry(f"{window_width}x{window_height}")
    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()
    x = (screen_width - window_width) // 2
    y = (screen_height - window_height) // 2
    root.geometry(f"+{x}+{y}")
 
    button_frame = tk.Frame(root)
    button_frame.pack(pady=20)
 
    row_val = tk.StringVar(value="10")
    col_val = tk.StringVar(value="10")
    mine_val = tk.StringVar(value="")
 
    # Grid size row
    tk.Label(button_frame, text='Grid Size', font=('calibre', 10, 'bold')).grid(
        row=0, column=0, padx=10, sticky='e')
    tk.Entry(button_frame, textvariable=row_val, width=5).grid(row=0, column=1, padx=5)
    tk.Label(button_frame, text='x', font=('calibre', 10, 'bold')).grid(row=0, column=2)
    tk.Entry(button_frame, textvariable=col_val, width=5).grid(row=0, column=3, padx=5)
 
    # Mines row
    tk.Label(button_frame, text='Mines', font=('calibre', 10, 'bold')).grid(
        row=1, column=0, padx=10, pady=8, sticky='e')
    mine_entry = tk.Entry(button_frame, textvariable=mine_val, width=5)
    mine_entry.grid(row=1, column=1, padx=5)
    tk.Label(button_frame, text='(leave blank for random)', font=('calibre', 8),
             fg='gray').grid(row=1, column=2, columnspan=2, sticky='w')
 
    # Start button
    tk.Button(button_frame, text="Start", padx=20, pady=10,
              command=left_click).grid(row=2, column=0, columnspan=4, pady=6)
 
    tk.Label(root,
             text="Instructions:\n"
                  " i) Left-click to reveal\n"
                  "ii) Right-click to flag (F)\n"
                  "iii) Beware of the Mines! (M)").pack()
 
    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.mainloop()
 
 
# Start socket server before menu
t = threading.Thread(target=start_server, daemon=True)
t.start()
 
backToMainMenu()
