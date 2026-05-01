class Reporter:
    def __init__(self, use_colors=False):
        self.use_colors = use_colors

    def report_result(self, result):
        print('\n=== Execution Result ===')
        print(f'Status         : {result.status}')
        print(f'Function calls : {len(result.calls)}')
        print()
        print('Step-by-step verdicts:')
        for call in result.calls:
            verdict = call.verdict or '??'
            out = str(call.output_state)[:120].replace('\n', ' ')
            print(f'  [{verdict:<9}] {call.name}()')
            if call.verdict_reason:
                print(f'               reason: {call.verdict_reason}')
        print()
        if result.errors:
            print(f'Findings ({len(result.errors)} issue(s)):')
            for err in result.errors:
                print(f'  line {err.lineno}: {err.error_type} -- {err.error_message}')
        else:
            print('Findings: no issues detected')
