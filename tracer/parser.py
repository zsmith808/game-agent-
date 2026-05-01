import ast
from dataclasses import dataclass, field


@dataclass
class FunctionInfo:
    name: str
    source: str
    docstring: str
    lineno: int


@dataclass
class ParsedScript:
    source: str
    functions: dict   # name -> FunctionInfo
    call_order: list  # list of (func_name, lineno)


def parse_source(source: str) -> ParsedScript:
    tree = ast.parse(source)
    source_lines = source.splitlines()
    functions = {}

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            func_lines = source_lines[node.lineno - 1:node.end_lineno]
            functions[node.name] = FunctionInfo(
                name=node.name,
                source='\n'.join(func_lines),
                docstring=ast.get_docstring(node) or '',
                lineno=node.lineno,
            )

    # Collect top-level calls in order (state = func(state) lines in agent main)
    call_order = []
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.Assign):
            if isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name):
                name = node.value.func.id
                if name in functions:
                    call_order.append((name, node.lineno))

    return ParsedScript(source=source, functions=functions, call_order=call_order)
