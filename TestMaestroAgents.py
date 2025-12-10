import os
import sys
import subprocess
from collections import Counter

LOG_DIR = "ab_logs"
GAMES_EACH_SIDE = 30
BOARD_SIZE = 11

MAESTRO_NEW = "agents.Group7.MaestroAgent MaestroAgent"
MAESTRO_OLD = "agents.Group7.MaestroBaseAgent MaestroBaseAgent"

def run_game(p1, p2, log_path, p1_name, p2_name):
    cmd = [
        sys.executable, "Hex.py",
        "-b", str(BOARD_SIZE),
        "-p1", p1,
        "-p1Name", p1_name,
        "-p2", p2,
        "-p2Name", p2_name,
        "-l", log_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode, (result.stdout or "") + "\n" + (result.stderr or "")

def parse_winner(log_path):
    with open(log_path, "r", encoding="utf-8") as f:
        lines = [ln.strip() for ln in f if ln.strip()]
    for ln in reversed(lines):
        if ln.startswith("winner,"):
            parts = ln.split(",")
            return parts[1], parts[2]
    return None, None

def main():
    os.makedirs(LOG_DIR, exist_ok=True)

    wins = Counter()
    reasons = Counter()
    missing = 0

    # NEW as P1
    for i in range(GAMES_EACH_SIDE):
        log_path = os.path.join(LOG_DIR, f"new_p1_game_{i+1}.log")
        code, output = run_game(MAESTRO_NEW, MAESTRO_OLD, log_path, "MaestroNEW", "MaestroOLD")

        if code != 0 or not os.path.exists(log_path):
            missing += 1
            print(f"\n[GAME FAILED OR NO LOG] new_p1_game_{i+1}")
            print(output)
            continue

        w, r = parse_winner(log_path)
        if w: wins[w] += 1
        if r: reasons[r] += 1

    # OLD as P1
    for i in range(GAMES_EACH_SIDE):
        log_path = os.path.join(LOG_DIR, f"old_p1_game_{i+1}.log")
        code, output = run_game(MAESTRO_OLD, MAESTRO_NEW, log_path, "MaestroOLD", "MaestroNEW")

        if code != 0 or not os.path.exists(log_path):
            missing += 1
            print(f"\n[GAME FAILED OR NO LOG] old_p1_game_{i+1}")
            print(output)
            continue

        w, r = parse_winner(log_path)
        if w: wins[w] += 1
        if r: reasons[r] += 1

    print("\n=== A/B RESULTS ===")
    print(f"Missing logs / failed games: {missing}")
    print("Wins:")
    for k, v in wins.items():
        print(f"  {k}: {v}")
    print("Reasons:")
    for k, v in reasons.items():
        print(f"  {k}: {v}")

    new_wins = wins.get("MaestroNEW", 0)
    old_wins = wins.get("MaestroOLD", 0)
    total = new_wins + old_wins
    if total:
        print(f"\nMaestroNEW win rate (logged): {100 * new_wins / total:.1f}%")

if __name__ == "__main__":
    main()
