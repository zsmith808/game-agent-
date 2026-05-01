import copy
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class FunctionCallRecord:
    name: str
    lineno: int
    input_state: Any
    output_state: Any
    verdict: Optional[str] = None
    verdict_reason: Optional[str] = None


@dataclass
class Error:
    lineno: int
    error_type: str
    error_message: str


@dataclass
class ExecutionResult:
    status: str
    reason: str
    calls: list
    errors: list
    final_state: Any = None


class TracingExecutor:
    def __init__(self, parsed, judge=None, continue_on_error=True):
        self.parsed = parsed
        self.judge = judge
        self.continue_on_error = continue_on_error

    def execute(self) -> ExecutionResult:
        calls = []
        errors = []

        # Split source into pre-main (imports + defs + setup) and main body
        marker = '# --- agent main ---'
        if marker in self.parsed.source:
            pre_main = self.parsed.source.split(marker)[0]
        else:
            pre_main = self.parsed.source

        # Execute pre-main to get functions defined and initial state set
        namespace = {}
        try:
            exec(compile(pre_main, '<tracer-setup>', 'exec'), namespace)
        except Exception as e:
            return ExecutionResult(status='ERROR', reason=f'setup failed: {e}', calls=[], errors=[])

        state = namespace.get('state')

        # Execute each step individually, capturing I/O
        for func_name, lineno in self.parsed.call_order:
            func = namespace.get(func_name)
            if func is None:
                errors.append(Error(lineno=lineno, error_type='NameError', error_message=f'{func_name} not defined'))
                continue

            input_snapshot = _safe_copy(state)

            try:
                state = func(state)
            except Exception as e:
                errors.append(Error(lineno=lineno, error_type='RuntimeError', error_message=str(e)))
                if not self.continue_on_error:
                    return ExecutionResult(status='ERROR', reason=str(e), calls=calls, errors=errors)
                continue

            output_snapshot = _safe_copy(state)
            record = FunctionCallRecord(
                name=func_name,
                lineno=lineno,
                input_state=input_snapshot,
                output_state=output_snapshot,
            )

            if self.judge:
                func_info = self.parsed.functions.get(func_name)
                verdict, reason = self.judge.verdict(
                    func_name=func_name,
                    docstring=func_info.docstring if func_info else '',
                    input_state=input_snapshot,
                    output_state=output_snapshot,
                )
                record.verdict = verdict
                record.verdict_reason = reason
                if verdict == 'INCORRECT':
                    errors.append(Error(
                        lineno=func_info.lineno if func_info else lineno,
                        error_type='LogicError',
                        error_message=reason,
                    ))

            calls.append(record)

        return ExecutionResult(
            status='SUCCESS',
            reason='completed',
            calls=calls,
            errors=errors,
            final_state=state,
        )


def _safe_copy(state):
    try:
        return copy.deepcopy(state)
    except Exception:
        return str(state)
