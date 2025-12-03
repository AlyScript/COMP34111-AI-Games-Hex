import math
import random
import time
from copy import deepcopy

from src.AgentBase import AgentBase
from src.Board import Board
from src.Colour import Colour
from src.Move import Move


class UnionFind:
    def __init__(self, size):
        self.size = size
        self.n_cells = size * size
        self.RED_TOP = self.n_cells
        self.RED_BOT = self.n_cells + 1
        self.BLUE_LEFT = self.n_cells + 2
        self.BLUE_RIGHT = self.n_cells + 3

        self.parent = list(range(self.n_cells + 4))
        self.board_status = [None] * self.n_cells
        self.empty_cells = set(range(self.n_cells))

    def find(self, i):
        path = []
        root = i
        while self.parent[root] != root:
            path.append(root)
            root = self.parent[root]
        for node in path:
            self.parent[node] = root
        return root

    def union(self, i, j):
        root_i = self.find(i)
        root_j = self.find(j)
        if root_i != root_j:
            self.parent[root_i] = root_j

    def place(self, idx, colour_enum):
        if idx not in self.empty_cells:
            return
        self.empty_cells.remove(idx)
        self.board_status[idx] = colour_enum

        r, c = divmod(idx, self.size)

        if colour_enum == Colour.RED:
            if r == 0:
                self.union(idx, self.RED_TOP)
            if r == self.size - 1:
                self.union(idx, self.RED_BOT)
        elif colour_enum == Colour.BLUE:
            if c == 0:
                self.union(idx, self.BLUE_LEFT)
            if c == self.size - 1:
                self.union(idx, self.BLUE_RIGHT)

        neighbors = [
            (r - 1, c),
            (r - 1, c + 1),
            (r, c - 1),
            (r, c + 1),
            (r + 1, c - 1),
            (r + 1, c),
        ]
        for nr, nc in neighbors:
            if 0 <= nr < self.size and 0 <= nc < self.size:
                n_idx = nr * self.size + nc
                if self.board_status[n_idx] == colour_enum:
                    self.union(idx, n_idx)

    def check_win(self, colour_enum):
        if colour_enum == Colour.RED:
            return self.find(self.RED_TOP) == self.find(self.RED_BOT)
        else:
            return self.find(self.BLUE_LEFT) == self.find(self.BLUE_RIGHT)

    def clone(self):
        new_obj = object.__new__(UnionFind)
        new_obj.size = self.size
        new_obj.n_cells = self.n_cells
        new_obj.RED_TOP = self.RED_TOP
        new_obj.RED_BOT = self.RED_BOT
        new_obj.BLUE_LEFT = self.BLUE_LEFT
        new_obj.BLUE_RIGHT = self.BLUE_RIGHT
        new_obj.parent = self.parent[:]
        new_obj.board_status = self.board_status[:]
        new_obj.empty_cells = self.empty_cells.copy()
        return new_obj


class RaveNode:
    def __init__(self, parent=None, move=None):
        self.parent = parent
        self.move = move
        self.children = []
        self.untried_moves = None
        self.wins = 0
        self.visits = 0
        self.amaf_wins = 0
        self.amaf_visits = 0


class MaestroAgent(AgentBase):
    def __init__(self, colour: Colour):
        self.colour = colour
        self.opponent_colour = Colour.opposite(colour)
        self.board_size = 11
        self.rave_bias = 3000  # Higher bias for "Maestro" level trust in AMAF
        self.time_limit_total = 290
        self.start_time_game = time.time()

    def get_time_allocation(self):
        elapsed = time.time() - self.start_time_game
        remaining = self.time_limit_total - elapsed
        if remaining < 5:
            return 0.1
        budget = remaining * 0.10
        return min(budget, 25.0)

    def make_move(self, turn: int, board: Board, opp_move: Move | None) -> Move:
        # 1. Stateless Identity Update
        self.opponent_colour = Colour.opposite(self.colour)

        # 2. Opening Book: Check for SWAP opportunity
        if turn == 1 and self.colour == Colour.BLUE:
            # Check center box (3-7)
            for x in range(3, 8):
                for y in range(3, 8):
                    if board.tiles[x][y].colour == Colour.RED:
                        return Move(-1, -1)

        # 3. Build Shadow Board
        shadow_board = UnionFind(self.board_size)
        for r in range(self.board_size):
            for c in range(self.board_size):
                tile_c = board.tiles[r][c].colour
                if tile_c == self.colour:
                    shadow_board.place(r * self.board_size + c, self.colour)
                elif tile_c == self.opponent_colour:
                    shadow_board.place(r * self.board_size + c, self.opponent_colour)

        # 4. RAVE MCTS
        root = RaveNode(parent=None, move=None)
        root.untried_moves = list(shadow_board.empty_cells)

        start_time = time.time()
        time_budget = self.get_time_allocation()

        while time.time() - start_time < time_budget:
            node = root
            sim_board = shadow_board.clone()

            # Selection
            while node.untried_moves == [] and node.children:
                node = self.select_child_rave(node)
                # Apply move
                depth = 0
                t = node
                while t.parent:
                    depth += 1
                    t = t.parent
                mover = self.colour if (depth % 2 != 0) else self.opponent_colour
                sim_board.place(node.move, mover)

            # Expansion
            if node.untried_moves:
                m = random.choice(node.untried_moves)
                depth = 0
                t = node
                while t.parent:
                    depth += 1
                    t = t.parent
                exp_mover = self.colour if (depth % 2 == 0) else self.opponent_colour

                sim_board.place(m, exp_mover)
                new_node = RaveNode(parent=node, move=m)
                node.untried_moves.remove(m)
                node.children.append(new_node)
                new_node.untried_moves = list(sim_board.empty_cells)
                node = new_node

            # Simulation (AMAF tracking)
            sim_red_moves = set()
            sim_blue_moves = set()

            depth = 0
            t = node
            while t.parent:
                depth += 1
                t = t.parent
            next_mover = self.opponent_colour if (depth % 2 != 0) else self.colour

            winner_colour = None
            if sim_board.check_win(self.colour):
                winner_colour = self.colour
            elif sim_board.check_win(self.opponent_colour):
                winner_colour = self.opponent_colour

            if not winner_colour:
                possible_moves = list(sim_board.empty_cells)
                random.shuffle(possible_moves)

                while possible_moves:
                    move_idx = possible_moves.pop()
                    sim_board.place(move_idx, next_mover)

                    if next_mover == Colour.RED:
                        sim_red_moves.add(move_idx)
                    else:
                        sim_blue_moves.add(move_idx)

                    if sim_board.check_win(next_mover):
                        winner_colour = next_mover
                        break
                    next_mover = (
                        self.opponent_colour
                        if next_mover == self.colour
                        else self.colour
                    )

            # Backpropagation
            winning_moves = (
                sim_red_moves if winner_colour == Colour.RED else sim_blue_moves
            )
            win_val = 1 if winner_colour == self.colour else 0

            while node:
                node.visits += 1
                node.wins += win_val
                if node.move is not None and node.move in winning_moves:
                    node.amaf_visits += 1
                    node.amaf_wins += win_val
                node = node.parent

        if not root.children:
            if not shadow_board.empty_cells:
                return Move(-1, -1)  # Should not happen
            m = list(shadow_board.empty_cells)[0]
            r, c = divmod(m, self.board_size)
            return Move(r, c)

        best = max(root.children, key=lambda c: c.visits)
        r, c = divmod(best.move, self.board_size)
        return Move(r, c)

    def select_child_rave(self, node):
        best_score = -float("inf")
        best_child = None

        for child in node.children:
            if child.visits == 0:
                # High urgency for unvisited nodes in RAVE
                return child

            uct_val = child.wins / child.visits
            amaf_val = (
                child.amaf_wins / child.amaf_visits if child.amaf_visits > 0 else 0
            )

            beta = math.sqrt(self.rave_bias / (3 * node.visits + self.rave_bias))
            expl = math.sqrt(2 * math.log(node.visits) / child.visits)

            score = (1 - beta) * uct_val + beta * amaf_val + expl

            if score > best_score:
                best_score = score
                best_child = child

        return best_child
