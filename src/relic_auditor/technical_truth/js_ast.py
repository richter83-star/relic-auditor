from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any


ADAPTER_VERSION = "js-token-ast-1"
KEYWORDS = {
    "if", "for", "while", "switch", "catch", "function", "return", "typeof",
    "delete", "void", "new", "class", "interface", "type", "enum", "import",
    "export", "from", "as", "const", "let", "var", "async", "await",
}


@dataclass(frozen=True)
class Token:
    kind: str
    value: str
    line: int
    offset: int


def parse_javascript_structure(text: str) -> dict[str, Any]:
    tokens = tokenize(text)
    pairs = _pairs(tokens)
    symbols: list[dict[str, Any]] = []
    imports: list[str] = []
    bindings: list[dict[str, str]] = []
    exports: set[str] = set()
    declaration_call_indexes: set[int] = set()
    i = 0
    while i < len(tokens):
        token = tokens[i]
        exported = token.value == "export"
        start = i + 1 if exported else i
        if exported and start < len(tokens) and tokens[start].value == "default":
            start += 1
        if start >= len(tokens):
            break
        current = tokens[start]
        if current.value == "import":
            end = _statement_end(tokens, start)
            source = _import_source(tokens, start, end)
            if source:
                imports.append(source)
                bindings.extend(_import_bindings(tokens, start, end, source))
            i = end + 1
            continue
        if current.value in {"function", "class", "interface", "type", "enum"}:
            name_index = _next_identifier(tokens, start + 1)
            if name_index is not None:
                name = tokens[name_index].value
                kind = current.value if current.value != "function" else "function"
                end_index = _declaration_end(tokens, name_index, pairs)
                symbols.append(_raw_symbol(kind, name, tokens[start].line, tokens[end_index].line, exported, start, end_index))
                if exported:
                    exports.add(name)
                if kind == "function":
                    paren = _find(tokens, name_index + 1, "(")
                    if paren is not None:
                        declaration_call_indexes.add(name_index)
                        symbols[-1]["parameters"] = _parameter_names(tokens, paren, pairs.get(paren))
                i = max(i + 1, end_index + 1)
                continue
        if current.value in {"const", "let", "var"}:
            name_index = _next_identifier(tokens, start + 1)
            if name_index is not None:
                arrow = _find_before_statement_end(tokens, name_index, "=>")
                if arrow is not None:
                    body_start = arrow + 1
                    end_index = pairs.get(body_start, _statement_end(tokens, body_start)) if body_start < len(tokens) and tokens[body_start].value == "{" else _statement_end(tokens, body_start)
                    name = tokens[name_index].value
                    symbols.append(_raw_symbol("function", name, tokens[start].line, tokens[end_index].line, exported, start, end_index))
                    if exported:
                        exports.add(name)
                    open_paren = _find(tokens, name_index + 1, "(")
                    if open_paren is not None and open_paren < arrow:
                        symbols[-1]["parameters"] = _parameter_names(tokens, open_paren, pairs.get(open_paren))
                    i = max(i + 1, end_index + 1)
                    continue
        i += 1

    calls: list[dict[str, Any]] = []
    for index, token in enumerate(tokens[:-1]):
        if token.kind != "identifier" or token.value in KEYWORDS or index in declaration_call_indexes:
            continue
        if index and tokens[index - 1].value in {".", "?."}:
            continue
        name, end = _member_name(tokens, index)
        if end + 1 >= len(tokens) or tokens[end + 1].value != "(":
            continue
        if index and tokens[index - 1].value in {"function", "class", "interface", "type"}:
            continue
        close = pairs.get(end + 1)
        owner = _owner(symbols, index)
        calls.append({
            "target_name": name,
            "line": token.line,
            "token_index": index,
            "caller_name": owner["name"] if owner else None,
            "argument_names": _argument_names(tokens, end + 1, close),
            "string_arguments": _string_arguments(tokens, end + 1, close),
        })

    env_reads = sorted({tokens[i + 4].value for i in range(len(tokens) - 4) if [t.value for t in tokens[i:i + 4]] == ["process", ".", "env", "."] and tokens[i + 4].kind == "identifier"})
    for symbol in symbols:
        body = text[_offset_for_line(text, symbol["start_line"]):_offset_for_line(text, symbol["end_line"] + 1)]
        symbol["stub"] = bool(re.search(r"throw\s+new\s+Error\s*\([^)]*(?:not implemented|todo)|^\s*(?:return\s+)?(?:null|undefined|false|true|\{\}|\[\])\s*;?\s*$", body, re.I | re.M))
        symbol["todo"] = bool(re.search(r"\b(?:TODO|FIXME|deprecated)\b", body, re.I))
    return {
        "tokens": len(tokens),
        "symbols": symbols,
        "imports": sorted(set(imports)),
        "import_bindings": sorted(bindings, key=lambda item: (item["local"], item["source"], item["imported"])),
        "exports": sorted(exports),
        "calls": calls,
        "environment_reads": env_reads,
        "parse_errors": _balance_errors(tokens, pairs),
    }


def tokenize(text: str) -> list[Token]:
    tokens: list[Token] = []
    i = 0
    line = 1
    while i < len(text):
        char = text[i]
        if char.isspace():
            line += char == "\n"
            i += 1
            continue
        if text.startswith("//", i):
            end = text.find("\n", i)
            if end < 0:
                break
            i = end
            continue
        if text.startswith("/*", i):
            end = text.find("*/", i + 2)
            end = len(text) - 2 if end < 0 else end
            line += text[i:end + 2].count("\n")
            i = end + 2
            continue
        if char in "'\"`":
            quote, start, start_line = char, i, line
            i += 1
            while i < len(text):
                if text[i] == "\\":
                    i += 2
                    continue
                if text[i] == quote:
                    i += 1
                    break
                line += text[i] == "\n"
                i += 1
            tokens.append(Token("string", text[start + 1:i - 1], start_line, start))
            continue
        match = re.match(r"[A-Za-z_$][A-Za-z0-9_$]*", text[i:])
        if match:
            value = match.group(0)
            tokens.append(Token("identifier", value, line, i))
            i += len(value)
            continue
        match = re.match(r"\d+(?:\.\d+)?", text[i:])
        if match:
            value = match.group(0)
            tokens.append(Token("number", value, line, i))
            i += len(value)
            continue
        operator = next((op for op in ("=>", "?.", "??", "===", "!==", "==", "!=", "<=", ">=", "&&", "||", "::", "...") if text.startswith(op, i)), None)
        if operator:
            tokens.append(Token("operator", operator, line, i))
            i += len(operator)
            continue
        tokens.append(Token("punctuation", char, line, i))
        i += 1
    return tokens


def _pairs(tokens):
    opens, pairs = [], {}
    matching = {")": "(", "]": "[", "}": "{"}
    for i, token in enumerate(tokens):
        if token.value in {"(", "[", "{"}:
            opens.append((token.value, i))
        elif token.value in matching:
            if opens and opens[-1][0] == matching[token.value]:
                _, start = opens.pop()
                pairs[start] = i
    return pairs


def _balance_errors(tokens, pairs):
    opening = sum(t.value in {"(", "[", "{"} for t in tokens)
    return max(0, opening - len(pairs))


def _raw_symbol(kind, name, start_line, end_line, exported, token_start, token_end):
    return {"kind": kind, "name": name, "start_line": start_line, "end_line": end_line, "exported": exported, "token_start": token_start, "token_end": token_end, "parameters": [], "stub": False, "todo": False}


def _next_identifier(tokens, start):
    for i in range(start, min(len(tokens), start + 8)):
        if tokens[i].kind == "identifier" and tokens[i].value not in KEYWORDS:
            return i
    return None


def _declaration_end(tokens, name_index, pairs):
    brace = _find(tokens, name_index + 1, "{")
    return pairs.get(brace, _statement_end(tokens, name_index)) if brace is not None else _statement_end(tokens, name_index)


def _statement_end(tokens, start):
    for i in range(start, len(tokens)):
        if tokens[i].value == ";":
            return i
    return len(tokens) - 1


def _find(tokens, start, value):
    for i in range(start, min(len(tokens), start + 80)):
        if tokens[i].value == value:
            return i
    return None


def _find_before_statement_end(tokens, start, value):
    for i in range(start, len(tokens)):
        if tokens[i].value == value:
            return i
        if tokens[i].value == ";":
            return None
    return None


def _import_source(tokens, start, end):
    strings = [t.value for t in tokens[start:end + 1] if t.kind == "string"]
    return strings[-1] if strings else None


def _import_bindings(tokens, start, end, source):
    result = []
    values = tokens[start:end + 1]
    if any(t.value == "{" for t in values):
        open_index = next(i for i, t in enumerate(values) if t.value == "{")
        close_index = next((i for i, t in enumerate(values[open_index + 1:], open_index + 1) if t.value == "}"), len(values))
        i = open_index + 1
        while i < close_index:
            if values[i].kind != "identifier" or values[i].value in {"type", "as"}:
                i += 1
                continue
            imported = values[i].value
            if i + 2 < close_index and values[i + 1].value == "as" and values[i + 2].kind == "identifier":
                local = values[i + 2].value
                i += 3
            else:
                local = imported
                i += 1
            result.append({"source": source, "imported": imported, "local": local})
            while i < close_index and values[i].value == ",":
                i += 1
    else:
        local = next((t.value for t in values[1:] if t.kind == "identifier" and t.value not in {"from", "type"}), None)
        if local:
            result.append({"source": source, "imported": "default", "local": local})
    return result


def _member_name(tokens, start):
    parts = [tokens[start].value]
    i = start
    while i + 2 < len(tokens) and tokens[i + 1].value in {".", "?."} and tokens[i + 2].kind == "identifier":
        parts.append(tokens[i + 2].value)
        i += 2
    return ".".join(parts), i


def _owner(symbols, token_index):
    candidates = [s for s in symbols if s["token_start"] <= token_index <= s["token_end"]]
    return min(candidates, key=lambda item: item["token_end"] - item["token_start"]) if candidates else None


def _parameter_names(tokens, open_index, close_index):
    if close_index is None:
        return []
    return [t.value for t in tokens[open_index + 1:close_index] if t.kind == "identifier" and t.value not in KEYWORDS]


def _argument_names(tokens, open_index, close_index):
    if close_index is None:
        return []
    return sorted({t.value for t in tokens[open_index + 1:close_index] if t.kind == "identifier" and t.value not in KEYWORDS})


def _string_arguments(tokens, open_index, close_index):
    if close_index is None:
        return []
    return [t.value for t in tokens[open_index + 1:close_index] if t.kind == "string"]


def _offset_for_line(text, line):
    if line <= 1:
        return 0
    offset = 0
    for _ in range(line - 1):
        found = text.find("\n", offset)
        if found < 0:
            return len(text)
        offset = found + 1
    return offset
