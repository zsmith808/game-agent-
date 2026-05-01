#!/usr/bin/env python3
"""
Actions module - Individual player actions for Avalon.
Contains the Player dataclass and all LLM-powered actions a player can take.
"""

import json
import os
import random
import time
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from dotenv import load_dotenv

load_dotenv()

from openai import OpenAI

# Initialize OpenAI client with Groq endpoint
client = OpenAI(
    base_url="https://api.groq.com/openai/v1",
    api_key=os.getenv("GROQ_API_KEY")
)


@dataclass
class Player:
    name: str
    team: str = ""
    model: str = "llama-3.3-70b-versatile - on_demand"
    memory: List[Dict] = field(default_factory=list)


def call_llm(prompt: str, max_tokens: int = 300, player_name: str = "", retry: bool = False) -> str:
    """
    Call Groq LLM with JSON mode.
    Retries once if invalid JSON, falls back to phase-specific default.
    """
    messages = [{"role": "user", "content": prompt}]
    if retry:
        messages.append({"role": "assistant", "content": "Please return only valid JSON matching the requested schema."})

    # Rate limit: 30 RPM = 1 request every 2 seconds
    time.sleep(2)

    try:
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=messages,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
            timeout=30
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"LLM call error for {player_name}: {e}", flush=True)
        return "{}"


def _parse_llm_json(response: str, player_name: str, fallback: dict, max_tokens: int = 300) -> dict:
    """Parse LLM JSON response, retry once on failure, return fallback if still invalid."""
    try:
        return json.loads(response)
    except json.JSONDecodeError:
        print(f"Invalid JSON from {player_name}, retrying...")
        retry_response = call_llm("Please return only valid JSON.", max_tokens=max_tokens, player_name=player_name, retry=True)
        try:
            return json.loads(retry_response)
        except json.JSONDecodeError:
            print(f"Retry failed for {player_name}, using fallback.")
            return fallback


def propose_team(leader: Player, team_size: int, round_num: int, all_players: List[Player]) -> Dict:
    """Individual leader action: propose a team for the mission."""
    player_names = [p.name for p in all_players]
    
    # Build memory summary for prompt
    memory_summary = []
    for entry in leader.memory:
        memory_summary.append(f"Round {entry['round_num']}: Leader {entry['captain']} proposed {entry['team']}, mission {'passed' if entry['mission_passed'] else 'failed'}, discussion: {entry['discussion_responses']}")
    
    # Build structured JSON input
    input_data = {
        "context": {
            "game": "Resistance: Avalon",
            "your_team": leader.team,
            "your_name": leader.name,
            "goal": "Good team wins if 3+ missions pass; Evil wins if 3+ missions fail."
        },
        "phase": "proposal",
        "game_state": {
            "round_num": round_num,
            "team_size": team_size,
            "all_players": player_names
        },
        "memory": memory_summary,
        "possible_actions": {
            "type": "propose_team",
            "team_size": team_size,
            "eligible_players": player_names,
            "constraint": f"select exactly {team_size} players"
        },
        "private_info": {
            "your_team": leader.team,
            "evil_allies": [] if leader.team == "good" else [p.name for p in all_players if p.team == "evil" and p.name != leader.name]
        }
    }

    prompt = f"""
You are {leader.name}, playing on the {leader.team} team in Resistance: Avalon.
As mission leader for round {round_num}, you must propose a team of {team_size} players.

All players: {', '.join(player_names)}

Your private info: You are on the {leader.team} team.
{f"Your evil allies: {[p.name for p in all_players if p.team == 'evil' and p.name != leader.name]}" if leader.team == "evil" else ""}

Previous rounds (MEMORY):
{chr(10).join(memory_summary) if memory_summary else "No previous rounds."}

STRATEGY:
- Good team: Pick players who seem trustworthy based on past discussions and mission results.
- Evil team: Pick players that help you sabotage, or frame good players.
- Consider who was on failed missions (suspicious) vs passed missions (trustworthy).

Propose a team of {team_size} players from: {', '.join(player_names)}.

Respond with JSON: {{"team": ["Name1", "Name2"], "reasoning": "explain your strategy based on above info"}}
"""
    response = call_llm(prompt, max_tokens=150, player_name=leader.name)
    fallback = {"team": [leader.name] + [p.name for p in all_players if p.name != leader.name][:team_size-1],
                "reasoning": "I choose based on my observations."}
    data = _parse_llm_json(response, leader.name, fallback, max_tokens=150)

    return {
        "team": data.get("team", [leader.name]),
        "reasoning": data.get("reasoning", "")
    }


def vote_on_team(player: Player, team: List[str], round_num: int, all_players: List[Player], good_wins: int, evil_wins: int, discussion: List[Dict]) -> Dict:
    """Individual player action: vote on the proposed team."""
    player_names = [p.name for p in all_players]
    
    # Build memory summary for prompt
    memory_summary = []
    for entry in player.memory:
        memory_summary.append(f"Round {entry['round_num']}: Leader {entry['captain']} proposed {entry['team']}, mission {'passed' if entry['mission_passed'] else 'failed'}, discussion: {entry['discussion_responses']}")
    
    # Build discussion summary
    discussion_summary = []
    for d in discussion:
        discussion_summary.append(f"{d['player']} ({d['team']}): {d['text']}")
    
    input_data = {
        "context": {
            "game": "Resistance: Avalon",
            "your_team": player.team,
            "your_name": player.name,
            "goal": "Good team wins if 3+ missions pass; Evil wins if 3+ missions fail."
        },
        "phase": "vote",
        "game_state": {
            "round_num": round_num,
            "proposed_team": team,
            "good_wins": good_wins,
            "evil_wins": evil_wins,
            "all_players": player_names
        },
        "memory": memory_summary,
        "discussion": discussion_summary,
        "possible_actions": {
            "type": "vote",
            "options": ["approve", "reject"]
        },
        "private_info": {
            "your_team": player.team,
            "evil_allies": [] if player.team == "good" else [p.name for p in all_players if p.team == "evil" and p.name != player.name]
        }
    }

    prompt = f"""
You are {player.name}, playing on the {player.team} team in Resistance: Avalon.
Vote on the proposed team: {', '.join(team)}.

Current game state: Round {round_num}, Good wins: {good_wins}/3, Evil wins: {evil_wins}/3.

Previous rounds (MEMORY):
{chr(10).join(memory_summary) if memory_summary else "No previous rounds."}

Discussion about this team:
{chr(10).join(discussion_summary) if discussion_summary else "No discussion."}

STRATEGY:
- Good team: Approve teams that seem trustworthy based on past behavior. Reject suspicious teams.
- Evil team: Reject good teams to stall. Approve teams that include evil allies or frame good players.
- Consider: Who was on failed missions? Who is acting suspiciously?

Respond with JSON: {{"vote": "approve" or "reject", "reasoning": "explain your strategic reasoning based on above info"}}
"""
    response = call_llm(prompt, max_tokens=200, player_name=player.name)
    
    fallback = {
        "vote": "approve" if player.team == "good" else "reject",
        "reasoning": "Good team looks trustworthy." if player.team == "good" else "I have concerns about this team."
    }
    data = _parse_llm_json(response, player.name, fallback, max_tokens=200)
    
    return {
        "vote": data.get("vote", fallback["vote"]),
        "reasoning": data.get("reasoning", fallback["reasoning"])
    }


def run_discussion(players: List[Player], team: List[str], round_num: int, good_wins: int, evil_wins: int) -> List[Dict]:
    """Run discussion phase where each player speaks."""
    discussions = []
    player_names = [p.name for p in players]

    for player in players:
        input_data = {
            "context": {
                "game": "Resistance: Avalon",
                "your_team": player.team,
                "goal": "Good team wins if 3+ missions pass; Evil wins if 3+ missions fail."
            },
            "phase": "discussion",
            "game_state": {
                "round_num": round_num,
                "proposed_team": team,
                "good_wins": good_wins,
                "evil_wins": evil_wins,
                "all_players": player_names
            },
            "memory": player.memory,
            "possible_actions": {
                "type": "discuss",
                "format": "1-2 sentence comment about the proposed team"
            },
            "private_info": {
                "your_team": player.team,
                "evil_allies": [] if player.team == "good" else [p.name for p in players if p.team == "evil" and p.name != player.name]
            }
        }

        prompt = f"""
You are {player.name} ({player.team} team).
Discuss the proposed team: {', '.join(team)}.
Provide a 1-2 sentence comment about who to trust.
Respond with JSON: {{"comment": "your 1-2 sentence comment"}}
"""
        response = call_llm(prompt, max_tokens=150, player_name=player.name)
        fallback = {"comment": f"I've been observing the group dynamics. We need to be strategic about our team selection."}
        data = _parse_llm_json(response, player.name, fallback, max_tokens=150)
        
        comment = data.get("comment", fallback["comment"])
        discussions.append({
            "player": player.name,
            "text": comment,
            "team": player.team
        })

    return discussions


def execute_mission(player: Player, round_num: int, good_wins: int, evil_wins: int) -> Dict:
    """Individual team member action: pass or fail the mission."""
    input_data = {
        "context": {
            "game": "Resistance: Avalon",
            "your_team": player.team,
            "goal": "Good team wins if 3+ missions pass; Evil wins if 3+ missions fail."
        },
        "phase": "mission",
        "game_state": {
            "round_num": round_num,
            "good_wins": good_wins,
            "evil_wins": evil_wins
        },
        "memory": player.memory,
        "possible_actions": {
            "type": "execute_mission",
            "options": ["success"] if player.team == "good" else ["success", "fail"]
        },
        "private_info": {
            "your_team": player.team,
            "evil_allies": []  # No allies on mission team for this action
        }
    }

    prompt = f"""
You are {player.name} ({player.team} team).
Execute the mission: choose to pass (success) or fail (if evil).
Current game state: Round {round_num}, Good wins: {good_wins}, Evil wins: {evil_wins}.
Respond with JSON: {{"action": "success" or "fail", "reasoning": "why"}}
"""
    response = call_llm(prompt, max_tokens=150, player_name=player.name)
    
    # Good players forced to success
    if player.team == "good":
        fallback = {"action": "success", "reasoning": f"As {player.name}, I must succeed for the good team."}
    else:
        fallback = {"action": "fail", "reasoning": f"Strategic choice as {player.name} (evil) - sabotage the mission."}
    
    data = _parse_llm_json(response, player.name, fallback, max_tokens=150)
    
    # Enforce good players only succeed
    action = data.get("action", fallback["action"])
    if player.team == "good":
        action = "success"
    
    return {
        "action": action,
        "reasoning": data.get("reasoning", fallback["reasoning"])
    }
