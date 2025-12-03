import heapq
import math
import time

from src.AgentBase import AgentBase
from src.Board import Board
from src.Colour import Colour
from src.Move import Move


class MinimaxAgent(AgentBase):
    def __init__(self, colour: Colour):
        self.colour = colour
        self.opponent_colour = Colour.opposite(colour)
        self.board_size = 11
        self.time_limit = 25.0  # Seconds per move
        self.start_time = 0

    def make_move(self, turn: int, board: Board, opp_move: Move | None) -> Move:
        # Stateless identity check
        self.opponent_colour = Colour.opposite(self.colour)

        # Opening book: Swap if P2 and center is taken
        if turn == 1 and self.colour == Colour.BLUE:
            for x in range(3, 8):
                for y in range(3, 8):
                    if board.tiles[x][y].colour == Colour.RED:
                        return Move(-1, -1)

        self.start_time = time.time()
        best_move = None

        # Iterative Deepening
        # We start at depth 1 and go deeper until time runs out
        for depth in range(1, 10):
            try:
                score, move = self.alphabeta(board, depth, -math.inf, math.inf, True)
                if move:
                    best_move = move

                # If we found a winning move, stop immediately
                if score == math.inf:
                    break

            except TimeoutError:
                break

        if best_move is None:
            # Fallback to first available move
            for i in range(self.board_size):
                for j in range(self.board_size):
                    if board.tiles[i][j].colour is None:
                        return Move(i, j)

        return best_move

    def alphabeta(self, board, depth, alpha, beta, maximizing_player):
        # Time check
        if time.time() - self.start_time > self.time_limit:
            raise TimeoutError()

        if depth == 0:
            return self.evaluate(board), None

        possible_moves = []
        # Optimization: Look at neighbors of occupied cells first (Locality)
        # For simplicity in this snippet, we scan all.
        for i in range(self.board_size):
            for j in range(self.board_size):
                if board.tiles[i][j].colour is None:
                    possible_moves.append(Move(i, j))

        if not possible_moves:
            return self.evaluate(board), None

        best_move = possible_moves[0]

        if maximizing_player:
            max_eval = -math.inf
            for move in possible_moves:
                # Make move
                board.tiles[move.x][move.y].colour = self.colour

                eval_score, _ = self.alphabeta(board, depth - 1, alpha, beta, False)

                # Undo move
                board.tiles[move.x][move.y].colour = None

                if eval_score > max_eval:
                    max_eval = eval_score
                    best_move = move
                alpha = max(alpha, eval_score)
                if beta <= alpha:
                    break
            return max_eval, best_move
        else:
            min_eval = math.inf
            for move in possible_moves:
                # Make move
                board.tiles[move.x][move.y].colour = self.opponent_colour

                eval_score, _ = self.alphabeta(board, depth - 1, alpha, beta, True)

                # Undo move
                board.tiles[move.x][move.y].colour = None

                if eval_score < min_eval:
                    min_eval = eval_score
                    best_move = move
                beta = min(beta, eval_score)
                if beta <= alpha:
                    break
            return min_eval, best_move

    def evaluate(self, board):
        """
        Heuristic: (Opponent Shortest Path) - (My Shortest Path)
        If I have a short path, score is high.
        If opponent has a short path, score is low.
        """
        my_path = self.dijkstra(board, self.colour)
        opp_path = self.dijkstra(board, self.opponent_colour)

        if my_path == 0:
            return math.inf  # I won
        if opp_path == 0:
            return -math.inf  # Opponent won

        return opp_path - my_path

    def dijkstra(self, board, colour):
        """Finds shortest path for 'colour' to connect their sides."""
        # 0 = Occupied by self
        # 1 = Empty
        # inf = Occupied by opponent

        size = self.board_size
        pq = []  # Priority Queue: (cost, x, y)
        costs = {}

        # Initialize sources
        if colour == Colour.RED:  # Top to Bottom
            target_row = size - 1
            for col in range(size):
                tile = board.tiles[0][col]
                cost = (
                    0
                    if tile.colour == colour
                    else (1 if tile.colour is None else math.inf)
                )
                if cost < math.inf:
                    heapq.heappush(pq, (cost, 0, col))
                    costs[(0, col)] = cost
        else:  # Left to Right
            target_col = size - 1
            for row in range(size):
                tile = board.tiles[row][0]
                cost = (
                    0
                    if tile.colour == colour
                    else (1 if tile.colour is None else math.inf)
                )
                if cost < math.inf:
                    heapq.heappush(pq, (row, 0, cost))  # Note: structure match
                    heapq.heappush(pq, (cost, row, 0))
                    costs[(row, 0)] = cost

        min_dist = math.inf

        visited = set()

        while pq:
            cost, r, c = heapq.heappop(pq)

            if (r, c) in visited:
                continue
            visited.add((r, c))

            # Goal check
            if (colour == Colour.RED and r == size - 1) or (
                colour == Colour.BLUE and c == size - 1
            ):
                return cost

            # Neighbors
            # [-1, -1, 0, 1, 1, 0]
            # [0, 1, 1, 0, -1, -1]
            neighbors = [
                (r - 1, c),
                (r - 1, c + 1),
                (r, c - 1),
                (r, c + 1),
                (r + 1, c - 1),
                (r + 1, c),
            ]

            for nr, nc in neighbors:
                if 0 <= nr < size and 0 <= nc < size:
                    tile = board.tiles[nr][nc]
                    move_cost = (
                        0
                        if tile.colour == colour
                        else (1 if tile.colour is None else math.inf)
                    )

                    if move_cost < math.inf:
                        new_cost = cost + move_cost
                        if new_cost < costs.get((nr, nc), math.inf):
                            costs[(nr, nc)] = new_cost
                            heapq.heappush(pq, (new_cost, nr, nc))

        return math.inf
