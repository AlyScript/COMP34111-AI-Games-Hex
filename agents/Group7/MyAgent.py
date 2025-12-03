import math
import random
import time
from copy import deepcopy

from src.AgentBase import AgentBase
from src.Board import Board
from src.Colour import Colour
from src.Move import Move
from src.Tile import Tile


class UnionFind:
    """
    A fast data structure to track connectivity.
    Essential for running thousands of MCTS simulations quickly.
    """

    def __init__(self, size):
        self.size = size
        self.n_cells = size * size
        # 4 virtual nodes: Top, Bottom (Red), Left, Right (Blue)
        self.RED_TOP = self.n_cells
        self.RED_BOT = self.n_cells + 1
        self.BLUE_LEFT = self.n_cells + 2
        self.BLUE_RIGHT = self.n_cells + 3

        # Parent array for Union-Find
        self.parent = list(range(self.n_cells + 4))
        self.board_status = [None] * self.n_cells  # Tracks who occupies which cell
        self.empty_cells = set(range(self.n_cells))

        # Pre-connect virtual nodes for edge cases logic
        # (Handled dynamically during moves to keep init fast)

    def find(self, i):
        """Path compression find."""
        if self.parent[i] != i:
            self.parent[i] = self.find(self.parent[i])
        return self.parent[i]

    def union(self, i, j):
        """Union two sets."""
        root_i = self.find(i)
        root_j = self.find(j)
        if root_i != root_j:
            self.parent[root_i] = root_j

    def place(self, idx, colour_enum):
        """Places a stone and connects neighbors."""
        if idx not in self.empty_cells:
            return

        self.empty_cells.remove(idx)
        self.board_status[idx] = colour_enum

        r, c = divmod(idx, self.size)

        # Connect to Virtual Nodes (Edges)
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

        # Connect to physical neighbors
        # Neighbours: (r-1, c), (r-1, c+1), (r, c-1), (r, c+1), (r+1, c-1), (r+1, c)
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

    def get_empty_moves(self):
        return list(self.empty_cells)

    def clone(self):
        """
        Fast manual copy of the board state.
        Avoiding deepcopy speeds up MCTS significantly.
        """
        # Create a new instance without calling __init__ (avoids re-creating lists)
        new_obj = object.__new__(UnionFind)

        # Copy scalar values
        new_obj.size = self.size
        new_obj.n_cells = self.n_cells
        new_obj.RED_TOP = self.RED_TOP
        new_obj.RED_BOT = self.RED_BOT
        new_obj.BLUE_LEFT = self.BLUE_LEFT
        new_obj.BLUE_RIGHT = self.BLUE_RIGHT

        # Fast slice copy for lists (much faster than deepcopy)
        new_obj.parent = self.parent[:]
        new_obj.board_status = self.board_status[:]
        new_obj.empty_cells = self.empty_cells.copy()

        return new_obj


class MCTSNode:
    def __init__(self, parent=None, move=None):
        self.parent = parent
        self.move = move  # The move that led to this state
        self.wins = 0
        self.visits = 0
        self.children = []
        self.untried_moves = None  # Will be populated on expansion


class VeryCleverAgent(AgentBase):
    def __init__(self, colour: Colour):
        self.colour = colour
        self.opponent_colour = Colour.opposite(colour)
        self.board_size = 11
        # Total time budget (5 minutes = 300 seconds).
        # We keep a safety buffer.
        self.time_limit_total = 290
        self.start_time_game = time.time()

        # Keep a persistent shadow board for MCTS to clone from
        self.shadow_board = UnionFind(self.board_size)
        self.turn_count = 0

    def get_time_allocation(self):
        """
        Dynamically allocate time based on game phase.
        Hex games usually last ~60 moves per player (120 total).
        """
        elapsed = time.time() - self.start_time_game
        remaining = self.time_limit_total - elapsed

        if remaining < 5:
            return 0.1  # Panic mode

        # Simple heuristic: Allocate ~5% of remaining time per move,
        # capped at 15 seconds to avoid timeouts.
        budget = remaining * 0.05
        return min(budget, 15.0)

    def make_move(self, turn: int, board: Board, opp_move: Move | None) -> Move:
        self.turn_count = turn

        # 1. Sync internal Shadow Board with Opponent's Move
        if opp_move and not opp_move.is_swap():
            idx = opp_move.x * self.board_size + opp_move.y
            self.shadow_board.place(idx, self.opponent_colour)

        # 2. Handle Swap Rule (Pie Rule) - WE SWAP
        # If we are P2 and P1 played a strong opening, we might want to swap.
        # (This logic remains the same as before)
        if turn == 1 and opp_move and not opp_move.is_swap():
            if 3 <= opp_move.x <= 7 and 3 <= opp_move.y <= 7:
                return Move(-1, -1)

        # 3. Handle Opponent Swap - THEY SWAPPED US
        # This is the FIX. If opponent swapped, we must flip our internal colours.
        if opp_move and opp_move.is_swap():
            self.colour, self.opponent_colour = self.opponent_colour, self.colour
            # Note: We don't need to update the board because a SWAP doesn't place a stone.
            # But subsequent MCTS runs must know we are now the OTHER colour.

        # 4. Run MCTS
        best_move = self.run_mcts()

        # 5. Apply our move to our shadow board
        idx = best_move.x * self.board_size + best_move.y
        self.shadow_board.place(idx, self.colour)

        return best_move

    def run_mcts(self) -> Move:
        root = MCTSNode(parent=None, move=None)
        root.untried_moves = self.shadow_board.get_empty_moves()

        start_time = time.time()
        time_budget = self.get_time_allocation()

        iter_count = 0

        while time.time() - start_time < time_budget:
            node = root
            simulation_board = self.shadow_board.clone()

            # --- Selection ---
            # Dig down until we find a node with untried moves or a terminal state
            while node.untried_moves == [] and node.children:
                node = self.select_child(node)
                # Apply move to simulation board
                r, c = divmod(node.move, self.board_size)
                # Determine whose move it was based on depth
                # Root is "Before My Move". Depth 1 is "After My Move" (Opponent turn)
                # This is tricky in MCTS.
                # Simplification: The node stores the move that JUST happened.
                # If node.parent is root, it was MY move.
                # If node.parent.parent is root, it was OPPONENT move.

                mover = (
                    self.colour
                    if (node.parent == root)
                    else (
                        self.opponent_colour
                        if node.parent.parent == root
                        else self.colour
                    )
                )
                # (Logic simplification: alternate colours based on depth)
                depth = 0
                temp = node
                while temp.parent:
                    depth += 1
                    temp = temp.parent

                mover = self.colour if (depth % 2 != 0) else self.opponent_colour
                simulation_board.place(node.move, mover)

            # --- Expansion ---
            if node.untried_moves:
                m = random.choice(node.untried_moves)
                # Determine who is moving
                depth = 0
                temp = node
                while temp.parent:
                    depth += 1
                    temp = temp.parent
                player_moving = (
                    self.colour if (depth % 2 == 0) else self.opponent_colour
                )

                simulation_board.place(m, player_moving)

                new_node = MCTSNode(parent=node, move=m)
                node.untried_moves.remove(m)
                node.children.append(new_node)
                new_node.untried_moves = simulation_board.get_empty_moves()
                node = new_node

            # --- Simulation (Rollout) ---
            # Play random moves until end
            current_turn_colour = (
                self.opponent_colour
                if (node.parent == root)
                else (self.colour if node.parent == None else self.opponent_colour)
            )
            # Fix turn logic: We just expanded 'player_moving', so next is opponent

            # Quick check if game already ended during Selection/Expansion
            if simulation_board.check_win(self.colour):
                result = 1  # We won
            elif simulation_board.check_win(self.opponent_colour):
                result = 0  # We lost
            else:
                # Rollout
                possible_moves = simulation_board.get_empty_moves()
                random.shuffle(possible_moves)

                # Alternate turns starting from who is next
                # If node just placed SELF, next is OPP
                # We need to track who is placing inside the loop

                # Hacky but fast depth calculation to know who moves next
                depth = 0
                temp = node
                while temp.parent:
                    depth += 1
                    temp = temp.parent

                next_mover = self.opponent_colour if (depth % 2 != 0) else self.colour

                while possible_moves:
                    move_idx = possible_moves.pop()
                    simulation_board.place(move_idx, next_mover)
                    if simulation_board.check_win(next_mover):
                        break
                    next_mover = (
                        self.opponent_colour
                        if next_mover == self.colour
                        else self.colour
                    )

                result = 1 if simulation_board.check_win(self.colour) else 0

            # --- Backpropagation ---
            while node:
                node.visits += 1
                node.wins += result
                node = node.parent

            iter_count += 1

        # Select best move (Robust Child: most visits)
        if not root.children:
            # Fallback if no time to expand (rare)
            m = random.choice(self.shadow_board.get_empty_moves())
            r, c = divmod(m, self.board_size)
            return Move(r, c)

        best_child = max(root.children, key=lambda c: c.visits)
        r, c = divmod(best_child.move, self.board_size)
        return Move(r, c)

    def select_child(self, node):
        """UCT Selection."""
        # UCB1 formula
        return max(
            node.children,
            key=lambda c: c.wins / c.visits
            + math.sqrt(2 * math.log(node.visits) / c.visits),
        )
