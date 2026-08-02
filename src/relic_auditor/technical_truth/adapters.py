from __future__ import annotations

import ast
import hashlib
import re
from collections import OrderedDict, namedtuple
from pathlib import PurePosixPath
from threading import RLock
from typing import Any

from .js_ast import ADAPTER_VERSION as JS_ADAPTER_VERSION, parse_javascript_structure


SUPPORTED = {".py": "python", ".js": "javascript", ".jsx": "javascript", ".ts": "typescript", ".tsx": "typescript"}
OTHER_SOURCE = {".java", ".cs", ".go", ".rs", ".rb", ".php", ".swift", ".kt", ".c", ".cc", ".cpp", ".h", ".hpp", ".sql", ".sh"}
PYTHON_ADAPTER_VERSION = "python-ast-3"
_PARSE_CACHE_MAXSIZE = 10_000
_PARSE_CACHE: OrderedDict[tuple[str, str, str], dict[str, Any]] = OrderedDict()
_PARSE_CACHE_LOCK = RLock()
_PARSE_CACHE_HITS = 0
_PARSE_CACHE_MISSES = 0
_CacheInfo = namedtuple("CacheInfo", "hits misses maxsize currsize")


def stable_id(prefix: str, *parts: str) -> str:
    return f"{prefix}_{hashlib.sha256(chr(31).join(parts).encode()).hexdigest()[:16]}"


def parse_source(path: str, text: str, family_id: str) -> dict[str, Any]:
    """Parse source without retaining the complete source text in the cache key."""
    global _PARSE_CACHE_HITS, _PARSE_CACHE_MISSES
    text_digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    cache_key = (path, text_digest, family_id)
    with _PARSE_CACHE_LOCK:
        cached = _PARSE_CACHE.get(cache_key)
        if cached is not None:
            _PARSE_CACHE.move_to_end(cache_key)
            _PARSE_CACHE_HITS += 1
            return cached
        _PARSE_CACHE_MISSES += 1

    parsed = _parse_source(path, text, family_id)
    with _PARSE_CACHE_LOCK:
        _PARSE_CACHE[cache_key] = parsed
        _PARSE_CACHE.move_to_end(cache_key)
        while len(_PARSE_CACHE) > _PARSE_CACHE_MAXSIZE:
            _PARSE_CACHE.popitem(last=False)
    return parsed


def _parse_source(path: str, text: str, family_id: str) -> dict[str, Any]:
    language = SUPPORTED.get(PurePosixPath(path).suffix.lower())
    if not language:
        return {"path": path, "project_family_id": family_id, "language": "unsupported", "status": "unsupported", "symbols": [], "references": [], "risks": []}
    try:
        return _python(path, text, family_id) if language == "python" else _javascript(path, text, family_id, language)
    except (SyntaxError, ValueError, RecursionError) as exc:
        return {"path": path, "project_family_id": family_id, "language": language, "status": "invalid_syntax", "error": type(exc).__name__, "symbols": [], "references": [], "risks": []}
    except Exception as exc:
        return {"path": path, "project_family_id": family_id, "language": language, "status": "parser_failure", "error": type(exc).__name__, "symbols": [], "references": [], "risks": []}


def parse_cache_info():
    with _PARSE_CACHE_LOCK:
        return _CacheInfo(
            _PARSE_CACHE_HITS,
            _PARSE_CACHE_MISSES,
            _PARSE_CACHE_MAXSIZE,
            len(_PARSE_CACHE),
        )


def _python(path: str, text: str, family_id: str) -> dict[str, Any]:
    tree = ast.parse(text, filename=path)
    symbols, refs, risks = [], [], []
    imports = []
    import_bindings = []
    env_reads = set()
    parents = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[child] = parent
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
                import_bindings.append(
                    {
                        "source": alias.name,
                        "imported": alias.name,
                        "local": alias.asname or alias.name.split(".")[0],
                    }
                )
        elif isinstance(node, ast.ImportFrom):
            source = f"{'.' * node.level}{node.module or ''}"
            if source:
                imports.append(source)
            for alias in node.names:
                import_bindings.append(
                    {
                        "source": source,
                        "imported": alias.name,
                        "local": alias.asname or alias.name,
                    }
                )
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            kind = "class" if isinstance(node, ast.ClassDef) else "function"
            decorators = [_name(item) for item in node.decorator_list]
            symbol = _symbol(path, family_id, "python", kind, node.name, node.lineno, getattr(node, "end_lineno", node.lineno), decorators, node.name.startswith("_") is False)
            if kind == "function":
                symbol["parameters"] = [arg.arg for arg in node.args.args]
                symbol["stub"] = _python_stub(node)
                symbol["todo"] = any(isinstance(child, (ast.Constant,)) and isinstance(getattr(child, "value", None), str) and re.search(r"\b(?:TODO|FIXME|deprecated)\b", child.value, re.I) for child in ast.walk(node))
            symbols.append(symbol)
        if isinstance(node, ast.Call):
            target = _name(node.func)
            owner = _python_owner(node, parents)
            refs.append({"kind": "calls", "source_file": path, "target_name": target, "line": node.lineno, "caller_name": owner.name if owner else None, "argument_names": sorted({_name(arg) for arg in node.args if _name(arg)}), "string_arguments": [arg.value for arg in node.args if isinstance(arg, ast.Constant) and isinstance(arg.value, str)], "confidence": 0.94, "method": "python_ast"})
            if target in {"subprocess.run", "subprocess.call", "os.system", "eval", "exec", "pickle.loads"}:
                risks.append({"path": path, "line": node.lineno, "indicator": target, "severity": "review", "note": "Static structural risk indicator; not executed or dynamically validated."})
        if isinstance(node, ast.Subscript) and _name(node.value) in {"os.environ", "environ"}:
            if isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, str):
                env_reads.add(node.slice.value)
        if isinstance(node, ast.Call) and _name(node.func) in {"os.getenv", "environ.get"} and node.args and isinstance(node.args[0], ast.Constant):
            env_reads.add(str(node.args[0].value))
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load) and node.id.startswith("TODO"):
            refs.append({"kind": "todo", "source_file": path, "target_name": node.id, "line": node.lineno, "confidence": 1.0, "method": "python_ast"})
    return {"path": path, "project_family_id": family_id, "language": "python", "status": "success", "adapter": PYTHON_ADAPTER_VERSION, "imports": sorted(set(imports)), "import_bindings": sorted(import_bindings, key=lambda item: (item["local"], item["source"])), "exports": sorted(s["name"] for s in symbols if s["exported"]), "environment_reads": sorted(env_reads), "symbols": symbols, "references": refs, "risks": risks}


def _javascript(path: str, text: str, family_id: str, language: str) -> dict[str, Any]:
    parsed = parse_javascript_structure(text)
    symbols, refs, risks = [], [], []
    for raw in parsed["symbols"]:
        symbol = _symbol(path, family_id, language, raw["kind"], raw["name"], raw["start_line"], raw["end_line"], [], raw["exported"])
        symbol["parameters"] = raw["parameters"]
        symbol["stub"] = raw["stub"]
        symbol["todo"] = raw["todo"]
        symbols.append(symbol)
    for call in parsed["calls"]:
        refs.append({"kind": "calls", "source_file": path, "target_name": call["target_name"], "line": call["line"], "caller_name": call["caller_name"], "argument_names": call["argument_names"], "string_arguments": call["string_arguments"], "confidence": 0.88, "method": "js_token_ast"})
    for indicator in ("child_process.exec", "spawn(", "eval(", "new Function(", "dangerouslySetInnerHTML"):
        if indicator in text:
            risks.append({"path": path, "line": _line(text, indicator), "indicator": indicator.rstrip("("), "severity": "review", "note": "Static structural risk indicator; not executed or dynamically validated."})
    status = "partial" if parsed["parse_errors"] else "success"
    return {"path": path, "project_family_id": family_id, "language": language, "status": status, "adapter": JS_ADAPTER_VERSION, "imports": parsed["imports"], "import_bindings": parsed["import_bindings"], "exports": parsed["exports"], "environment_reads": parsed["environment_reads"], "symbols": symbols, "references": refs, "risks": risks}


def _symbol(path, family, language, kind, name, start, end, decorators, exported):
    return {"symbol_id": stable_id("sym", family, path, kind, name, str(start)), "project_family_id": family, "file": path, "language": language, "kind": kind, "name": name, "qualified_name": f"{PurePosixPath(path).with_suffix('').as_posix().replace('/', '.')}.{name}", "exported": exported, "visibility": "public" if exported else "module", "lines": {"start": start, "end": end}, "parameters": [], "return_type": None, "decorators": decorators, "annotations": [], "confidence": 0.98 if language == "python" else 0.86}


def _name(node):
    if isinstance(node, ast.Name): return node.id
    if isinstance(node, ast.Attribute): return f"{_name(node.value)}.{node.attr}".strip(".")
    if isinstance(node, ast.Call): return _name(node.func)
    try: return ast.unparse(node)
    except Exception: return ""


def _python_owner(node, parents):
    current = parents.get(node)
    while current is not None:
        if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return current
        current = parents.get(current)
    return None


def _python_stub(node):
    body = list(node.body)
    if not body:
        return True
    meaningful = [item for item in body if not (isinstance(item, ast.Expr) and isinstance(item.value, ast.Constant) and isinstance(item.value.value, str))]
    if not meaningful:
        return True
    if len(meaningful) == 1:
        item = meaningful[0]
        if isinstance(item, ast.Pass):
            return True
        if isinstance(item, ast.Raise) and isinstance(item.exc, ast.Call) and _name(item.exc.func) in {"NotImplementedError", "Exception"}:
            return True
        if isinstance(item, ast.Return) and isinstance(item.value, ast.Constant) and item.value.value in {None, False, True}:
            return True
    return False


def _line(text, token): return text[:text.find(token)].count("\n") + 1
def _block_end(text, offset, start): return start + text[offset:offset + 4000].split("}")[0].count("\n")
def _unbalanced(text): return abs(text.count("{") - text.count("}")) > 1
def _mask_comments_strings(text):
    value = re.sub(r"(?s)/\*.*?\*/", " ", text)
    value = re.sub(r"(?m)//.*$", " ", value)
    return re.sub(r"""(['"`])(?:\\.|(?!\1).)*\1""", lambda m: " " * len(m.group(0)), value)
