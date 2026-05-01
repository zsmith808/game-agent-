import json
import re
from openai import OpenAI


class LLMJudge:
    def __init__(self, api_key: str, script_goal: str, model: str = 'llama-3.3-70b-versatile'):
        self.client = OpenAI(api_key=api_key, base_url='https://api.groq.com/openai/v1')
        self.model = model
        self.script_goal = script_goal

    def verdict(self, func_name: str, docstring: str, input_state, output_state):
        prompt = f"""You are auditing one step of an AI agent pipeline.

Overall goal: {self.script_goal}

Function: {func_name}
Docstring: {docstring}

Input state:
{_fmt(input_state)}

Output state:
{_fmt(output_state)}

Does the output match what the docstring says this step should do?
Reply with EXACTLY one of these two formats:

VERDICT: CORRECT

or

VERDICT: INCORRECT
REASON: <one sentence>"""

        resp = self.client.chat.completions.create(
            model=self.model,
            max_tokens=120,
            messages=[{'role': 'user', 'content': prompt}],
        )
        text = resp.choices[0].message.content.strip()

        if 'INCORRECT' in text:
            m = re.search(r'REASON:\s*(.+)', text, re.DOTALL)
            reason = m.group(1).strip() if m else 'output does not match docstring'
            return 'INCORRECT', reason
        return 'CORRECT', ''


def _fmt(state) -> str:
    if isinstance(state, dict):
        filtered = {k: v for k, v in state.items() if v is not None and k != 'api_key'}
        try:
            return json.dumps(filtered, indent=2, default=str)[:600]
        except Exception:
            return str(filtered)[:600]
    return str(state)[:600]
