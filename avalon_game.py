#!/usr/bin/env python3
"""
Avalon Game Engine - Runs multi-agent Avalon games with LLM reasoning.
Outputs game state as JSON after each phase for the viewer.
"""

import json
import os
import time
import random
import sys
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Optional
import actions
from actions import Player
import subprocess
import atexit

# ─── Configuration ─────────────────────────────────────────

PLAYER_NAMES = ["Alice", "Bob", "Charlie", "Diana", "Eve"]

MISSION_SIZES_5P = [2, 2, 2, 2, 2]

# ─── Server Management ──────────────────────────────────────

server_process = None

def start_server():
    """Start the HTTP server as a subprocess."""
    global server_process
    
    # Check if already running
    if server_process and server_process.poll() is None:
        return
    
    # Kill any existing process on port 8080
    try:
        result = subprocess.run(['lsof', '-ti:8080'], capture_output=True, text=True)
        if result.stdout.strip():
            pids = result.stdout.strip().split('\n')
            for pid in pids:
                if pid:
                    try:
                        os.kill(int(pid), 9)
                        print(f"Killed existing process on port 8080 (PID: {pid})")
                    except:
                        pass
            time.sleep(1)
    except:
        pass
    
    # Start server as subprocess
    server_process = subprocess.Popen(
        [sys.executable, "avalon_server.py"],
        cwd=Path(__file__).parent,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    print(f"Server started (PID: {server_process.pid})")
    time.sleep(2)  # Wait for server to bind to port

def stop_server():
    """Stop the HTTP server subprocess."""
    global server_process
    if server_process:
        server_process.terminate()
        try:
            server_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server_process.kill()
        print("Server stopped")

# Register cleanup on exit
atexit.register(stop_server)


# ─── Game State ──────────────────────────────────────────────

@dataclass
class GameState:
    game_id: str
    players: List[Player] = field(default_factory=list)
    rounds: List[Dict] = field(default_factory=list)
    current_round: int = 0
    mission_leader: int = 0
    good_wins: int = 0
    evil_wins: int = 0
    winner: str = ""
    game_log: List[Dict] = field(default_factory=list)


# ─── Role Assignment ──────────────────────────────────────

def assign_roles(players: List[Player]) -> None:
    """Randomly assign good/evil teams (3 good, 2 evil)."""
    teams = ["good"] * 3 + ["evil"] * 2
    random.shuffle(teams)
    for player, team in zip(players, teams):
        player.team = team


# ─── Save Game State ─────────────────────────────────────

def save_game_state(state: GameState, filename: str = "current_game.json"):
    """Save game state to JSON for the viewer."""
    players_list = []
    for p in state.players:
        player_dict = {
            "name": p.name,
            "team": p.team,
            "model": p.model
        }
        players_list.append(player_dict)
    
    data = {
        "game_id": state.game_id,
        "players": players_list,
        "rounds": state.rounds,
        "current_round": state.current_round,
        "good_wins": state.good_wins,
        "evil_wins": state.evil_wins,
        "winner": state.winner,
        "game_log": state.game_log,
        "mission_leader": state.mission_leader,
        "mission_sizes": MISSION_SIZES_5P
    }
    # Write to temp file first, then rename (atomic write)
    temp_file = filename + ".tmp"
    with open(temp_file, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(temp_file, filename)
    print(f"Game state saved to {filename}")


# ─── Manual Mode Control ────────────────────────────────

NEXT_ACTION_FLAG = Path(__file__).parent / ".next_action_triggered"
WAITING_FLAG = Path(__file__).parent / ".waiting_for_next"


def _wait_for_next_action():
    """Wait for the viewer to signal 'Next Action'."""
    WAITING_FLAG.write_text("waiting")
    print("  → Waiting for 'Next Action' signal...")

    while not NEXT_ACTION_FLAG.exists():
        time.sleep(0.5)

    NEXT_ACTION_FLAG.unlink(missing_ok=True)
    WAITING_FLAG.unlink(missing_ok=True)
    print("  → Continuing...")


# ─── Main Game Loop ─────────────────────────────────────

def run_game(autoMode=False):
    """Run a complete Avalon game."""
    start_server()
    
    print("=" * 60)
    print("THE RESISTANCE: AVALON - Game Simulation")
    print("=" * 60)
    print("THE RESISTANCE: AVALON - Game Simulation")
    print("=" * 60)

    # Initialize
    state = GameState(game_id=f"game_{int(time.time())}")
    state.players = [Player(name) for name in PLAYER_NAMES]
    assign_roles(state.players)

    print("\nPlayers:")
    for p in state.players:
        print(f"  {p.name}: ({p.team})")
    print()

    save_game_state(state)
    print(f"  → Game state updated! (Visible in viewer at http://localhost:8080)")
    if not autoMode:
        print(f"  Waiting for 'Next Action' click in viewer...")
        _wait_for_next_action()

    # Game loop (up to 5 rounds)
    for round_num in range(1, 6):
        if state.winner:
            break

        print(f"\n{'─' * 60}")
        print(f"ROUND {round_num}")
        print(f"{'─' * 60}")

        state.current_round = round_num
        round_data = {"round": round_num, "phases": []}

        # Phase1: Proposal
        print(f"\n[Phase] Mission {round_num} - Team Proposal")
        leader = state.players[state.mission_leader % len(state.players)]
        team_size = MISSION_SIZES_5P[round_num - 1]
        proposal = actions.propose_team(leader, team_size, round_num, state.players)
        print(f"Leader: {leader.name} ({leader.team})")
        print(f"Proposed team: {', '.join(proposal.get('team', []))}")
        print(f"Reasoning: {proposal.get('reasoning', '')}")
        state.game_log.append({
            "phase": "proposal",
            "round": round_num,
            "leader": leader.name,
            "team": proposal.get("team", []),
            "reasoning": proposal.get("reasoning", "")
        })
        round_data["phases"].append({"type": "proposal", "data": proposal})
        save_game_state(state)
        if not autoMode:
            _wait_for_next_action()

        # Phase 2: Discussion
        print(f"\n[Phase] Discussion")
        discussions = actions.run_discussion(state.players, proposal.get("team", []), round_num, state.good_wins, state.evil_wins)
        for d in discussions:
            print(f"  [{d['player']} ({d['team']})]: {d['text']}")
        state.game_log.append({
            "phase": "discussion",
            "round": round_num,
            "content": discussions
        })
        round_data["phases"].append({"type": "discussion", "data": discussions})
        save_game_state(state)
        if not autoMode:
            _wait_for_next_action()

        # Phase 3: Vote
        print(f"\n[Phase] Voting")
        votes = {}
        vote_reasoning = {}
        for player in state.players:
            result = actions.vote_on_team(player, proposal.get("team", []), round_num, state.players, state.good_wins, state.evil_wins, discussions)
            votes[player.name] = result["vote"]
            vote_reasoning[player.name] = result["reasoning"]

        approved = sum(1 for v in votes.values() if v == "approve") > len(votes) / 2
        for player, vote in votes.items():
            print(f"  {player}: {vote.upper()} - {vote_reasoning.get(player, '')}")
        print(f"  → Proposal {'APPROVED' if approved else 'REJECTED'}")

        state.game_log.append({
            "phase": "vote",
            "round": round_num,
            "votes": votes,
            "reasoning": vote_reasoning,
            "approved": approved
        })
        round_data["phases"].append({"type": "vote", "data": {"votes": votes, "reasoning": vote_reasoning, "approved": approved}})
        save_game_state(state)
        if not autoMode:
            _wait_for_next_action()

        if not approved:
            print("\nProposal rejected! Moving to next leader.")
            state.mission_leader += 1
            state.rounds.append(round_data)
            if not autoMode:
                _wait_for_next_action()
            continue

        # Phase 4: Mission Execution
        print(f"\n[Phase] Mission Execution")
        results = []
        players_map = {p.name: p for p in state.players}
        for member_name in proposal.get("team", []):
            player = players_map.get(member_name)
            if not player:
                continue
            result = actions.execute_mission(player, round_num, state.good_wins, state.evil_wins)
            results.append({
                "player": member_name,
                "action": result["action"],
                "reasoning": result["reasoning"]
            })
            print(f"  {member_name} ({player.team}): {result['action'].upper()} - {result['reasoning']}")

        passed = all(r["action"] == "success" for r in results)
        print(f"  → Mission {'PASSED' if passed else 'FAILED'}")

        # Build discussion responses dict for memory
        discussion_responses = {}
        for d in discussions:
            discussion_responses[d["player"]] = d["text"]

        # Create memory entry for this round (public info for all players)
        memory_entry = {
            "round_num": round_num,
            "captain": leader.name,
            "team": proposal.get("team", []),
            "mission_passed": passed,
            "discussion_responses": discussion_responses
        }

        # Update memory for all players
        for player in state.players:
            player.memory.append(memory_entry)

        state.game_log.append({
            "phase": "mission",
            "round": round_num,
            "results": results,
            "passed": passed,
            "fails": sum(1 for r in results if r["action"] == "fail")
        })
        round_data["phases"].append({"type": "mission", "data": {"results": results, "passed": passed}})
        save_game_state(state)
        if not autoMode:
            _wait_for_next_action()

        # Update scores
        if passed:
            state.good_wins += 1
            print(f"\nGood wins mission! (Good: {state.good_wins}/3)")
        else:
            state.evil_wins += 1
            print(f"\nEvil wins mission! (Evil: {state.evil_wins}/3)")

        state.rounds.append(round_data)
        save_game_state(state)
        if not autoMode:
            _wait_for_next_action()

        # Check for winner
        if state.good_wins >= 3:
            print(f"\n{'=' * 60}")
            print("GOOD TEAM WINS THE GAME!")
            print(f"{'=' * 60}")
            state.winner = "good"
            break
        elif state.evil_wins >= 3:
            print(f"\n{'=' * 60}")
            print("EVIL TEAM WINS! (3 missions failed)")
            print(f"{'=' * 60}")
            state.winner = "evil"
            break

        state.mission_leader += 1

    # Final save
    save_game_state(state)
    print(f"\nFinal game state saved to current_game.json")
    print("=" * 60)


if __name__ == "__main__":
    auto_mode = "--auto" in sys.argv or "-a" in sys.argv
    NEW_GAME_FLAG = Path(__file__).parent / ".new_game_requested"

    try:
        while True:
            # Check if new game was requested
            if NEW_GAME_FLAG.exists():
                print("\n" + "=" * 60)
                print("NEW GAME REQUESTED - RESTARTING...")
                print("=" * 60 + "\n")
                NEW_GAME_FLAG.unlink(missing_ok=True)

            run_game(autoMode=auto_mode)
            print("\n" + "=" * 60)
            print("STARTING NEW GAME IN 3 SECONDS...")
            print("=" * 60 + "\n")
            time.sleep(3)
    except KeyboardInterrupt:
        print("\nGame stopped by user")
    finally:
        stop_server()
