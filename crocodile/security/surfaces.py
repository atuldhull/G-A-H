"""Static, conservative execution-surface checks on edit replacement text."""

import ast
import textwrap

MODULES = {
    "subprocess",
    "socket",
    "urllib",
    "http",
    "requests",
    "httpx",
    "ctypes",
    "winreg",
    "importlib",
    "marshal",
}
CALLS = {"eval", "exec", "compile", "__import__", "pickle.loads", "shutil.rmtree"}
PURE_BUILTINS = {
    "len",
    "range",
    "str",
    "int",
    "float",
    "bool",
    "list",
    "dict",
    "tuple",
    "set",
    "abs",
    "min",
    "max",
    "sum",
    "sorted",
    "enumerate",
    "zip",
    "repr",
    "ascii",
    "any",
    "all",
    "isinstance",
}


def changes_execution(replacement: str) -> bool:
    """Unknown syntax is conservative: a fragment may hide executable code."""
    if not replacement.strip():
        return False
    try:
        tree = ast.parse(textwrap.dedent(replacement))
    except (SyntaxError, ValueError, RecursionError):
        return True
    aliases = {}
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Name)
            and isinstance(node.ctx, ast.Store)
            and node.id == "pytest_plugins"
        ):
            return True
        if isinstance(node, ast.Import):
            for name in node.names:
                aliases[name.asname or name.name.split(".")[0]] = name.name
                if name.name.split(".")[0] in MODULES:
                    return True
        elif isinstance(node, ast.ImportFrom):
            for name in node.names:
                aliases[name.asname or name.name] = f"{node.module}.{name.name}"
            if (node.module or "").split(".")[0] in MODULES:
                return True
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        parts = []
        func = node.func
        while isinstance(func, ast.Attribute):
            parts.insert(0, func.attr)
            func = func.value
        if isinstance(func, ast.Name):
            parts.insert(0, aliases.get(func.id, func.id))
        else:
            return True
        name = ".".join(parts)
        if name in CALLS or name.split(".")[0] in MODULES:
            return True
        if name.startswith("os.") and name[3:].startswith(("system", "exec", "spawn")):
            return True
        if name not in PURE_BUILTINS:
            # Aliases imported before the replacement are not in this AST.
            return True
    return False
