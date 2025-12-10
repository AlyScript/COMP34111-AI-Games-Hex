import subprocess
from pathlib import Path
from collections import defaultdict
import itertools
import json
import re

ENGINE_CMD = ["python3", "Hex.py"]

AGENTS = {
    "Maestro": "agents.Group7.MaestroAgent MaestroAgent",
    "MCTS":    "agents.Group7.MctsAgent VeryCleverAgent",
    "AMAF":    "agents.Group7.AmafAgent AmafAgent",
    "Minimax": "agents.Group7.MinimaxAgent MinimaxAgent",
    "Naive":   "agents.DefaultAgents.NaiveAgent NaiveAgent",
}

BOARD_SIZE = 11
GAMES_PER_MATCHUP = 30
LOGS_DIR = Path("tournament_logs")
LOGS_DIR.mkdir(parents=True, exist_ok=True)
SUMMARY_JSON = Path("tournament_summary.json")


def run_game(p1_label, p1_spec, p2_label, p2_spec, log_path, board_size=11, verbose=False):
    cmd = (
        ENGINE_CMD
        + ["-b", str(board_size)]
        + ["-p1", p1_spec, "-p1Name", p1_label]
        + ["-p2", p2_spec, "-p2Name", p2_label]
        + ["-l", str(log_path)]
    )
    if verbose:
        cmd.append("-v")

    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode, result.stdout, result.stderr


def parse_game_log(log_path):
    lines = Path(log_path).read_text(errors="ignore").splitlines()
    winner = None
    reason = None

    # Find winner line from bottom
    for line in reversed(lines):
        if line.startswith("winner,"):
            parts = line.split(",")
            # expected: winner,<Name>,<Reason>
            if len(parts) >= 3:
                winner = parts[1].strip()
                reason = parts[2].strip()
            break

    total_time_ns = {}
    time_line_pattern = re.compile(r"^([^,]+),(\d+)$")
    for line in lines[::-1]:
        m = time_line_pattern.match(line.strip())
        if m and m.group(1) != "winner":
            name = m.group(1).strip()
            val = int(m.group(2))
            total_time_ns[name] = val
        # stop early once we've likely passed summary region
        if line.startswith("winner,"):
            # keep scanning a little above it, so don't break immediately
            continue

    return {
        "winner": winner,
        "reason": reason or "UNKNOWN",
        "total_time_ns": total_time_ns,
    }


# STATS AGGREGATION

def init_match_stats():
    return {
        "games": 0,
        "wins": defaultdict(int),          # wins[label]
        "wins_as_p1": defaultdict(int),    # wins_as_p1[label]
        "wins_as_p2": defaultdict(int),
        "reasons": defaultdict(int),       # reasons[reason]
        "unknown_winner": 0,
        # sum total time for label
        # "time_ns": defaultdict(int),
    }


def update_match_stats(stats, p1_label, p2_label, parsed):
    stats["games"] += 1

    winner = parsed["winner"]
    reason = parsed["reason"]
    stats["reasons"][reason] += 1

    if not winner:
        stats["unknown_winner"] += 1
    else:
        stats["wins"][winner] += 1
        if winner == p1_label:
            stats["wins_as_p1"][winner] += 1
        elif winner == p2_label:
            stats["wins_as_p2"][winner] += 1

    # accumulate total time if present
    for name, tns in parsed.get("total_time_ns", {}).items():
        stats["time_ns"][name] += tns


def pct(x, n):
    return (100.0 * x / n) if n else 0.0


# TOURNAMENT LOGIC

def play_matchup(labelA, specA, labelB, specB, games, board_size):
    """
    Plays a fair matchup:
    - alternates seats each game (A as P1 then A as P2)
    """
    stats = init_match_stats()
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    for i in range(games):
        if i % 2 == 0:
            p1_label, p1_spec = labelA, specA
            p2_label, p2_spec = labelB, specB
        else:
            p1_label, p1_spec = labelB, specB
            p2_label, p2_spec = labelA, specA

        log_path = LOGS_DIR / f"{labelA}_vs_{labelB}_g{i+1}.log"

        run_game(p1_label, p1_spec, p2_label, p2_spec,
                 log_path, board_size=board_size)
        parsed = parse_game_log(log_path)
        update_match_stats(stats, p1_label, p2_label, parsed)

    return stats


def print_matchup_summary(labelA, labelB, stats):
    g = stats["games"]
    wA = stats["wins"].get(labelA, 0)
    wB = stats["wins"].get(labelB, 0)

    print(f"\n=== {labelA} vs {labelB} ===")
    print(f"Games: {g}")
    print(f"{labelA} wins: {wA} ({pct(wA, g):.1f}%)")
    print(f"{labelB} wins: {wB} ({pct(wB, g):.1f}%)")
    print(f"{labelA} wins as P1: {stats['wins_as_p1'].get(labelA, 0)}")
    print(f"{labelA} wins as P2: {stats['wins_as_p2'].get(labelA, 0)}")
    print("Reasons:")
    for reason, count in sorted(stats["reasons"].items(), key=lambda x: -x[1]):
        print(f"  {reason}: {count}")

    # displaly time
    # if stats["time_ns"]:
    #     tA = stats["time_ns"].get(labelA, 0)
    #     tB = stats["time_ns"].get(labelB, 0)
    #     print("Approx total decision time (ns) from logs (if provided):")
    #     print(f"  {labelA}: {tA}")
    #     print(f"  {labelB}: {tB}")


def run_round_robin(agents_dict, games_per_matchup, board_size):
    labels = list(agents_dict.keys())

    all_results = {}
    league_table = {label: {"played": 0, "wins": 0, "losses": 0}
                    for label in labels}

    for labelA, labelB in itertools.combinations(labels, 2):
        specA = agents_dict[labelA]
        specB = agents_dict[labelB]

        stats = play_matchup(labelA, specA, labelB, specB,
                             games_per_matchup, board_size)
        print_matchup_summary(labelA, labelB, stats)

        all_results[f"{labelA}_vs_{labelB}"] = stats

        # update league table (simple W/L)
        g = stats["games"]
        wA = stats["wins"].get(labelA, 0)
        wB = stats["wins"].get(labelB, 0)

        league_table[labelA]["played"] += g
        league_table[labelB]["played"] += g
        league_table[labelA]["wins"] += wA
        league_table[labelB]["wins"] += wB
        league_table[labelA]["losses"] += (g - wA)
        league_table[labelB]["losses"] += (g - wB)

    return all_results, league_table


def print_league_table(league_table):
    print("\n==============================")
    print("         LEAGUE TABLE         ")
    print("==============================")

    sorted_rows = sorted(
        league_table.items(),
        key=lambda kv: (kv[1]["wins"], -kv[1]["losses"]),
        reverse=True
    )

    for label, row in sorted_rows:
        played = row["played"]
        wins = row["wins"]
        losses = row["losses"]
        winrate = pct(wins, played)
        print(f"{label:10s}  Played: {played:3d}  Wins: {wins:3d}  Losses: {losses:3d}  Win%: {winrate:5.1f}")


def serialize_for_json(obj):
    if isinstance(obj, defaultdict):
        obj = dict(obj)
    if isinstance(obj, dict):
        return {k: serialize_for_json(v) for k, v in obj.items()}
    return obj


def save_summary(all_results, league_table, path):
    payload = {
        "config": {
            "board_size": BOARD_SIZE,
            "games_per_matchup": GAMES_PER_MATCHUP,
            "agents": AGENTS,
        },
        "matchups": {
            k: serialize_for_json(v) for k, v in all_results.items()
        },
        "league_table": league_table,
    }
    path.write_text(json.dumps(payload, indent=2))
    print(f"\nSaved summary to: {path}")


if __name__ == "__main__":
    print("Starting Group7 tournament...")
    print(f"Board size: {BOARD_SIZE}")
    print(f"Games per matchup: {GAMES_PER_MATCHUP}")
    print("Agents:")
    for k in AGENTS:
        print(f"  - {k}")

    all_results, league_table = run_round_robin(
        AGENTS, GAMES_PER_MATCHUP, BOARD_SIZE)
    print_league_table(league_table)
    save_summary(all_results, league_table, SUMMARY_JSON)
