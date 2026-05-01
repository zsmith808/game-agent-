"""
Blackjack agent — ToyAgent + Tracer error-localization demo.

Three steps:
  1. build_prompt  — compose a simple HIT/STAND prompt
  2. call_llm      — ask Claude, store raw response
  3. parse_action  — extract the action (contains the bug)

The bug: parse_action matches the FIRST occurrence of HIT/STAND in the
full response instead of the dedicated ACTION: line. Claude's reasoning
often says things like "hitting here risks busting me" before concluding
"ACTION: STAND", so the wrong word gets picked — silently.

Run:
    export ANTHROPIC_API_KEY=sk-ant-...
    export OPENAI_API_KEY=sk-...        # used by Tracer's judge
    python blackjack_agent.py
"""

import sys
import os
import re
import openai
from dotenv import load_dotenv
load_dotenv()

_tracer_dir = os.environ.get('TRACER_DIR', os.path.join(os.path.dirname(__file__), 'tracer'))
sys.path.insert(0, _tracer_dir)

from toy_agent import ToyAgent

agent = ToyAgent(
    goal=(
        "Play one blackjack decision: call Claude with the player's hand and dealer card, "
        "then parse the action from the final 'ACTION: HIT' or 'ACTION: STAND' line. "
        "state['action'] must match state['expected_action']."
    )
)

agent.imports = [
    "import os",
    "import re",
    "import openai",
]

# Hand: 10 + 6 = 16 vs dealer 7, cautious strategy → correct answer is STAND
agent.setup = """
    state = {
        'hand_score': 16,
        'dealer_card': '7',
        'strategy': 'cautious',
        'api_key': os.environ.get('GROQ_API_KEY', ''),
        'prompt': None,
        'llm_response': None,
        'action': None,
        'expected_action': 'STAND',
    }
"""


@agent.add_step
def build_prompt(state):
    """Build a blackjack decision prompt.

    Adds state['prompt']: asks Claude to think step by step and end with
    exactly one line — 'ACTION: HIT' or 'ACTION: STAND'.
    """
    state['prompt'] = (
        f"You are a {state['strategy']} blackjack player.\n"
        f"Your hand totals {state['hand_score']}. Dealer shows {state['dealer_card']}.\n"
        f"Think step by step about whether to hit or stand.\n"
        f"End your response with exactly one line: ACTION: HIT  or  ACTION: STAND"
    )
    return state


@agent.add_step
def call_llm(state):
    """Send the prompt to Claude and store the raw text response.

    Reads state['prompt']; adds state['llm_response'].
    """
    import openai
    client = openai.OpenAI(api_key=state['api_key'], base_url='https://api.groq.com/openai/v1')
    message = client.chat.completions.create(
        model='llama-3.3-70b-versatile',
        max_tokens=300,
        messages=[{'role': 'user', 'content': state['prompt']}],
    )
    state['llm_response'] = message.choices[0].message.content
    return state


@agent.add_step
def parse_action(state):
    """Parse the final ACTION line from the LLM response.

    Reads state['llm_response']; sets state['action'] to 'HIT' or 'STAND'
    by finding the line that begins with 'ACTION:' and extracting the word
    that follows. Falls back to 'STAND' if no ACTION line is present.
    state['action'] should equal state['expected_action'].
    """
    import re
    text = state['llm_response']
    # BUG: matches the FIRST occurrence of HIT/STAND anywhere in the text,
    # not the dedicated ACTION: line — picks up chain-of-thought words like
    # "hitting here would bust me" before Claude's final ACTION: STAND.
    match = re.search(r'\b(HIT|STAND)\b', text)
    state['action'] = match.group(1) if match else 'STAND'
    return state


# ---------------------------------------------------------------------------

DEMO_HANDS = [
    {'hand_score': 16, 'dealer_card': '7',  'expected_action': 'STAND'},  # cautious: stand on 16
    {'hand_score': 11, 'dealer_card': '10', 'expected_action': 'HIT'},    # strong double-down hand
    {'hand_score': 19, 'dealer_card': 'A',  'expected_action': 'STAND'},  # obvious stand
    {'hand_score': 15, 'dealer_card': '10', 'expected_action': 'HIT'},    # dealer strong, must hit
    {'hand_score': 12, 'dealer_card': '4',  'expected_action': 'STAND'},  # dealer weak, don't risk bust
]

def make_initial_state(hand):
    return {
        **hand,
        'strategy': 'cautious',
        'api_key': os.environ.get('GROQ_API_KEY', ''),
        'prompt': None,
        'llm_response': None,
        'action': None,
    }


def localize(state):
    """Run each step individually and report which one produced wrong output."""
    findings = []

    s1 = build_prompt(state.copy())
    if 'ACTION: HIT' not in s1['prompt'] and 'ACTION: STAND' not in s1['prompt']:
        findings.append('build_prompt | LogicError | prompt missing ACTION instruction')
    else:
        findings.append('build_prompt | OK        | prompt contains ACTION instruction')

    s2 = call_llm(s1.copy())
    action_lines = [l for l in s2['llm_response'].splitlines() if l.strip().startswith('ACTION:')]
    if not action_lines:
        findings.append('call_llm     | LogicError | LLM response has no ACTION: line')
        llm_final = ''
    else:
        llm_final = action_lines[-1].strip()
        findings.append(f'call_llm     | OK        | LLM said: "{llm_final}"')

    s3 = parse_action(s2.copy())
    llm_intended = llm_final.replace('ACTION: ', '') if llm_final else 'UNKNOWN'
    if s3['action'] != llm_intended and llm_intended != 'UNKNOWN':
        findings.append(
            f'parse_action | LogicError | line {inspect.getsourcelines(parse_action)[1] + 12}: '
            f'extracted "{s3["action"]}" but ACTION: line says "{llm_intended}" '
            f'-- regex matched chain-of-thought word, not ACTION: line'
        )
    else:
        findings.append(f'parse_action | OK        | correctly extracted "{s3["action"]}" from ACTION: line')
        if s3['action'] != s3['expected_action']:
            findings.append(
                f'             | NOTE      | LLM chose "{s3["action"]}" but strategy expects '
                f'"{s3["expected_action"]}" -- LLM disagreed with expected strategy, not a parse bug'
            )

    return findings


if __name__ == '__main__':
    groq_key = os.environ.get('GROQ_API_KEY', '')

    # ── Play 5 hands ──────────────────────────────────────────────────────────
    print('=' * 60)
    print('BLACKJACK AGENT  —  5 hands')
    print('=' * 60)
    bug_hand = None
    for hand in DEMO_HANDS:
        result = agent.run_local(initial=make_initial_state(hand))
        correct = result['action'] == result['expected_action']
        status = 'OK' if correct else 'WRONG'
        print(f"  Hand {result['hand_score']:>2} vs dealer {result['dealer_card']:<2}  |  "
              f"expected {result['expected_action']:<5}  got {result['action']:<5}  [{status}]")
        if not correct and bug_hand is None:
            bug_hand = hand
    print()

    # ── Tracer audit on the first hand where the bug fired ────────────────────
    if bug_hand is None:
        print('No wrong answers this run — bug did not fire.')
        raise SystemExit(0)

    print('=' * 60)
    print(f"TRACER AUDIT  —  Hand {bug_hand['hand_score']} vs dealer {bug_hand['dealer_card']}")
    print('=' * 60)

    single_hand_agent = ToyAgent(goal=agent.goal)
    single_hand_agent.imports = agent.imports
    single_hand_agent.setup = f"""
    import os
    state = {{
        'hand_score': {bug_hand['hand_score']},
        'dealer_card': '{bug_hand['dealer_card']}',
        'strategy': 'cautious',
        'api_key': os.environ.get('GROQ_API_KEY', ''),
        'prompt': None,
        'llm_response': None,
        'action': None,
        'expected_action': '{bug_hand['expected_action']}',
    }}
    """
    for step in agent.steps:
        single_hand_agent.steps.append(step)

    audit_result = single_hand_agent.audit_with_tracer(api_key=groq_key)
    print()
    if audit_result.errors:
        print('Findings:')
        for err in audit_result.errors:
            print(f'  line {err.lineno}: {err.error_type} -- {err.error_message}')
    else:
        print('No issues detected (bug may not have fired on this LLM call).')
