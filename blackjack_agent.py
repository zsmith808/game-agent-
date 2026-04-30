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

_tracer_dir = os.environ.get('TRACER_DIR', '/Users/katyaogai/Tracer')
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

if __name__ == '__main__':
    print('=== Live demo: 5 hands ===\n')
    for hand in DEMO_HANDS:
        initial = {
            **hand,
            'strategy': 'cautious',
            'api_key': os.environ.get('GROQ_API_KEY', ''),
            'prompt': None,
            'llm_response': None,
            'action': None,
        }
        result = agent.run_local(initial=initial)
        correct = result['action'] == result['expected_action']
        print(f"Hand {result['hand_score']} vs dealer {result['dealer_card']}")
        print(f"  Expected : {result['expected_action']}")
        print(f"  Got      : {result['action']}  {'OK' if correct else '*** WRONG (bug fired!) ***'}")
        print(f"  Reasoning: {result['llm_response'][:300]}")
        print()

    print('=== Generated script (what Tracer will see) ===')
    print(agent.to_script())
    print()

    openai_key = os.environ.get('OPENAI_API_KEY')
    if not openai_key:
        print('OPENAI_API_KEY not set — skipping Tracer audit.')
        raise SystemExit(0)

    print('=== Tracer audit ===')
    result_audit = agent.audit_with_tracer(api_key=openai_key)
    print()
    print('=== Findings ===')
    for err in result_audit.errors:
        print(f'  line {err.lineno}: {err.error_type} -- {err.error_message}')
