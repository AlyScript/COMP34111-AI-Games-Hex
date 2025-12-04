Implements several agents, the most significant of which being `MaestroAgent`, a competitive Hex agent based on Monte Carlo Tree Search ([MCTS](https://en.wikipedia.org/wiki/Monte_Carlo_tree_search)) with significant optimizations applied.

### Key Approaches
- **RAVE (Rapid Action Value Estimation)**: Upgraded from standard [UCT](https://en.wikipedia.org/wiki/Upper_Confidence_Bound) to [RAVE](https://en.wikipedia.org/wiki/Monte_Carlo_tree_search#Improvements) ([All-Moves-As-First](https://users.soe.ucsc.edu/~dph/mypubs/AMAFpaperWithRef.pdf)). This updates statistics for every move in a winning simulation rather than just the root move
- **Union-Find Optimization**: Implements a lightweight Disjoint Set Union class with path compression. This replaces the default Board DFS for win-checks during simulations, reducing complexity from O(N) to nearly O(1)
- **Fast Cloning**: Replaces `deepcopy` with a manual `clone()` method for the shadow board, significantly increasing simulations per second
- [Swap rule](https://www.hexwiki.net/index.php/Swap_rule): Logic added to detect strong opening moves (center box) and trigger a SWAP
- **Time Management**: Dynamic time allocation based on the 5-minute total budget, decaying as the game progresses to prevent timeouts

### Testing and Validation
There are currently three competent test agents implemented:
- `MinimaxAgent`
- `AmafAgent`
- `MctsAgent`
