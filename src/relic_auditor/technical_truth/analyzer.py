from __future__ import annotations

import hashlib
import re
from collections import Counter, defaultdict, deque
from pathlib import PurePosixPath
from typing import Any

from ..models import AuditResult, FileRecord
from .adapters import (
    OTHER_SOURCE,
    PYTHON_ADAPTER_VERSION,
    SUPPORTED,
    parse_source,
    stable_id,
)
from .cache import ParseCache
from .js_ast import ADAPTER_VERSION as JS_ADAPTER_VERSION
from .lineage import inspect_git_lineage
from .schemas import (
    MIN_CONCLUSION_COVERAGE,
    TechnicalTruthConfig,
    TechnicalTruthResult,
)


def analyze_technical_truth(audit: AuditResult, config: TechnicalTruthConfig | None = None) -> TechnicalTruthResult:
    cfg = config or TechnicalTruthConfig()
    families = _families(audit, cfg.resolve_git_lineage)
    family_for = _family_lookup(families)
    cache = ParseCache(cfg.cache_path if cfg.use_persistent_cache else None)
    parse_results, unsupported = [], []
    for record in audit.files:
        suffix = record.extension
        family_id = family_for(record.path)
        if suffix not in SUPPORTED:
            if suffix in OTHER_SOURCE:
                unsupported.append({"path": record.path, "project_family_id": family_id, "language": suffix.lstrip(".") or "unknown", "language_hint": suffix, "status": "unsupported", "symbols": [], "references": [], "risks": []})
            continue
        if record.size > cfg.max_file_size:
            parse_results.append({"path": record.path, "project_family_id": family_id, "language": SUPPORTED[suffix], "status": "too_large", "symbols": [], "references": [], "risks": []})
            continue
        if not cfg.include_tests and record.role == "test":
            parse_results.append({"path": record.path, "project_family_id": family_id, "language": SUPPORTED[suffix], "status": "excluded_test", "symbols": [], "references": [], "risks": []})
            continue
        if record.text is None:
            parse_results.append({"path": record.path, "project_family_id": family_id, "language": SUPPORTED[suffix], "status": "binary_or_unreadable", "symbols": [], "references": [], "risks": []})
            continue
        adapter_version = PYTHON_ADAPTER_VERSION if suffix == ".py" else JS_ADAPTER_VERSION
        cache_key = cache.key(record.path, record.sha256 or hashlib.sha256(record.text.encode()).hexdigest(), family_id, adapter_version)
        cached = cache.get(cache_key)
        if cached is not None:
            parse_results.append(cached)
        else:
            parsed = parse_source(record.path, record.text, family_id)
            parse_results.append(parsed)
            cache.put(cache_key, parsed)
    parse_results.extend(unsupported)
    parse_results.sort(key=lambda item: item["path"])
    cache.save()
    symbols = sorted((s for result in parse_results for s in result.get("symbols", [])), key=lambda item: item["symbol_id"])
    surfaces = _surfaces(audit, symbols, family_for)
    graph = _graph(audit, parse_results, symbols, surfaces, cfg.max_graph_nodes, cfg.max_data_flow_edges)
    reachability = _reachability(symbols, graph, audit)
    workflows = _workflows(graph, surfaces, cfg.workflow_depth)
    capabilities = _capabilities(audit, workflows, surfaces, symbols, reachability)
    contradictions = _contradictions(
        audit,
        capabilities,
        surfaces,
        parse_results,
        family_for,
    )
    _apply_contradictions(capabilities, contradictions)
    summary = _summary(audit, parse_results, symbols, graph, families, workflows, capabilities, contradictions, surfaces)
    return TechnicalTruthResult(summary, symbols, graph, families, surfaces, workflows, capabilities, contradictions, reachability, parse_results)


def _families(audit, resolve_git=True):
    groups = defaultdict(list)
    roots = [project.root for project in audit.projects] or ["."]
    for root in roots:
        normalized = re.sub(r"(?i)([-_ ]?(backup|copy|old|archive|worktree|branch|pass)\d*)+$", "", root) or root
        groups[normalized].append(root)
    results = []
    lineage = inspect_git_lineage(audit.target, roots) if resolve_git else []
    lineage_by_root = {item["project_root"]: item for item in lineage}
    for name, members in sorted(groups.items()):
        records = [r for r in audit.files if any(root == "." or r.path.startswith(root + "/") for root in members)]
        fingerprints = sorted({r.sha256 for r in records if r.sha256})[:20]
        relationship = "independent_project" if len(members) == 1 else "shared_origin_repository"
        git_members = [lineage_by_root[member] for member in members if member in lineage_by_root]
        results.append({"schema_version": "1.0", "family_id": stable_id("family", name), "canonical_hint": name, "members": sorted(members), "relationship": relationship, "confidence": 0.95 if len(members) > 1 else 0.82 if git_members else 0.7, "evidence": {"normalized_name": name, "shared_file_hashes": fingerprints, "git_lineage": git_members}, "divergence_preserved": True, "family_timeline": [{"member": member, "head": lineage_by_root.get(member, {}).get("head"), "branch": lineage_by_root.get(member, {}).get("branch")} for member in sorted(members)], "merge_recommendation": "No automatic merge recommended; compare unique capabilities and compatibility first."})
    return results


def _family_lookup(families):
    pairs = [(member, f["family_id"]) for f in families for member in f["members"]]
    def lookup(path):
        matches = [(root, fid) for root, fid in pairs if root == "." or path.startswith(root + "/")]
        return max(matches, key=lambda pair: len(pair[0]))[1] if matches else stable_id("family", ".")
    return lookup


def _surfaces(audit, symbols, family_for):
    endpoints, ui, ui_screens, schemas, async_items, integrations, tests, risks, frameworks = [], [], [], [], [], [], [], [], []
    symbol_by_file = defaultdict(list)
    for symbol in symbols: symbol_by_file[symbol["file"]].append(symbol)
    for record in audit.files:
        text = record.text or ""
        if not text: continue
        family = family_for(record.path)
        is_test = record.role == "test"
        if is_test:
            kind = "mock" if re.search(r"\b(mock|fixture|stub|fake)\b", text, re.I) else "test"
            tests.append({"surface_id": stable_id("test", record.path), "project_family_id": family, "file": record.path, "kind": kind, "strength": "low" if kind == "mock" else "moderate", "disabled": bool(re.search(r"\b(skip|xfail|todo)\b", text, re.I))})
        for match in re.finditer(r"""(?m)@(app|router)\.(get|post|put|patch|delete)\(\s*['"]([^'"]+)""", text):
            registered = match.group(1) == "app" or _router_registered(audit, record.path)
            endpoints.append(_endpoint(record.path, family, match.group(2), match.group(3), _next_symbol(symbol_by_file[record.path], _line(text, match.start())), "fastapi", registered, text))
        for match in re.finditer(r"""(?m)\b(app|router|fastify|server)\.(get|post|put|patch|delete)\(\s*['"]([^'"]+)""", text):
            registered = match.group(1) == "app" or _router_registered(audit, record.path)
            tail = text[match.end():match.end() + 160]
            callback = re.search(r"\s*,\s*([A-Za-z_$][\w$]*)", tail)
            handler = callback.group(1) if callback else _next_symbol(symbol_by_file[record.path], _line(text, match.start()))
            framework = "fastify" if match.group(1) == "fastify" else "express"
            endpoints.append(_endpoint(record.path, family, match.group(2), match.group(3), handler, framework, registered, text))
        for match in re.finditer(r"""(?m)@app\.route\(\s*['"]([^'"]+)['"][^)]*methods\s*=\s*\[\s*['"](\w+)""", text):
            endpoints.append(_endpoint(record.path, family, match.group(2), match.group(1), _next_symbol(symbol_by_file[record.path], _line(text, match.start())), "flask", True, text))
        for match in re.finditer(r"""(?m)\bpath\(\s*['"]([^'"]+)['"]\s*,\s*([A-Za-z_][\w]*)""", text):
            endpoints.append(_endpoint(record.path, family, "ANY", "/" + match.group(1).lstrip("/"), match.group(2), "django", True, text))
        if re.search(r"(?m)export\s+(?:async\s+)?function\s+(GET|POST|PUT|PATCH|DELETE)\b", text):
            method = re.search(r"(?m)export\s+(?:async\s+)?function\s+(GET|POST|PUT|PATCH|DELETE)\b", text).group(1)
            route = "/" + "/".join(part for part in PurePosixPath(record.path).parts if part not in {"app", "route.ts", "route.js"})[:-1]
            endpoints.append(_endpoint(record.path, family, method.lower(), route or "/", method, "nextjs", True, text))
        for match in re.finditer(r"""(?:fetch|axios\.(?:get|post|put|patch|delete))\(\s*['"`]([^'"`]+)""", text):
            ui.append({"surface_id": stable_id("ui", record.path, match.group(1), str(match.start())), "project_family_id": family, "type": "ui_action", "file": record.path, "action": "api_request", "target": match.group(1), "line": _line(text, match.start()), "mock_only": bool(re.search(r"\b(mockData|fixture|fakeReport)\b", text)), "confidence": 0.9})
        if record.extension in {".jsx", ".tsx"} or re.search(r"\bfrom\s+['\"]react['\"]", text):
            component = next((s for s in symbol_by_file[record.path] if s["kind"] in {"function", "class"} and (s["exported"] or s["name"][:1].isupper())), None)
            if component and re.search(r"<[A-Za-z][^>]*>", text):
                ui_screens.append({"surface_id": stable_id("ui-screen", record.path, component["name"]), "project_family_id": family, "type": "ui_screen", "file": record.path, "name": component["name"], "line": component["lines"]["start"], "mock_only": bool(re.search(r"\b(mockData|fixture|fakeReport|demoData)\b", text, re.I)), "confidence": 0.88})
        for match in re.finditer(r"(?m)^\s*(?:class\s+(\w+).*(?:Base|Model)|model\s+(\w+)|CREATE\s+TABLE\s+[\"]?(\w+))", text, re.I):
            name = next(group for group in match.groups() if group)
            schemas.append({"surface_id": stable_id("schema", record.path, name), "project_family_id": family, "type": "schema", "file": record.path, "name": name, "line": _line(text, match.start()), "confidence": 0.88})
        for match in re.finditer(r"""(?:queue\.add|enqueue|send_task|delay)\s*\(\s*['"]?([\w.-]+)?""", text):
            async_items.append({"surface_id": stable_id("producer", record.path, str(match.start())), "project_family_id": family, "type": "queue_producer", "file": record.path, "queue": match.group(1) or "unknown", "line": _line(text, match.start()), "confidence": 0.82})
        for match in re.finditer(r"""(?:new\s+Worker|process|@app\.task)\s*\(\s*['"]?([\w.-]+)?['"]?\s*(?:,\s*([A-Za-z_$][\w$]*))?""", text):
            async_items.append({"surface_id": stable_id("consumer", record.path, str(match.start())), "project_family_id": family, "type": "queue_consumer", "file": record.path, "queue": match.group(1) or "unknown", "handler": match.group(2), "line": _line(text, match.start()), "confidence": 0.8})
        for provider in ("stripe", "firebase", "supabase", "openai", "s3", "sendgrid", "twilio"):
            configured = bool(re.search(provider, text, re.I))
            called = bool(re.search(rf"\b{provider}\.\w+\s*\(", text, re.I))
            if configured:
                integrations.append({"surface_id": stable_id("integration", record.path, provider), "project_family_id": family, "type": "integration", "file": record.path, "provider": provider, "usage": "called" if called else "configuration_only", "confidence": 0.9 if called else 0.6})
        for item in _risk_indicators(record.path, text):
            risks.append({**item, "project_family_id": family})
        for framework, pattern in {
            "React": r"\b(?:from\s+['\"]react['\"]|React\.|<[A-Z][A-Za-z]+)",
            "Next.js": r"\b(?:from\s+['\"]next/|NextRequest|NextResponse)",
            "FastAPI": r"\b(?:from\s+fastapi|FastAPI\()",
            "Flask": r"\b(?:from\s+flask|Flask\()",
            "Django": r"\b(?:from\s+django|django\.)",
            "Express": r"\b(?:from\s+['\"]express['\"]|require\(['\"]express)",
            "Fastify": r"\b(?:from\s+['\"]fastify['\"]|fastify\.)",
            "BullMQ": r"\b(?:from\s+['\"]bullmq['\"]|new\s+Worker\()",
            "Celery": r"\b(?:from\s+celery|Celery\()",
            "Prisma": r"\bprisma\.\w+",
            "SQLAlchemy": r"\b(?:sqlalchemy|declarative_base|Session\()",
        }.items():
            if re.search(pattern, text, re.I):
                frameworks.append({"surface_id": stable_id("framework", record.path, framework), "project_family_id": family, "type": "framework", "file": record.path, "name": framework, "confidence": .9, "evidence_method": "import_or_runtime_convention"})
    return {"frameworks": _dedupe(frameworks), "endpoints": _dedupe(endpoints), "ui": _dedupe(ui), "ui_screens": _dedupe(ui_screens), "schemas": _dedupe(schemas), "async": _dedupe(async_items), "integrations": _dedupe(integrations), "tests": _dedupe(tests), "risk_indicators": _dedupe(risks)}


def _graph(audit, parsed, symbols, surfaces, limit, max_data_flow_edges):
    nodes, edges = [], []
    symbols_by_file = defaultdict(list)
    family_by_file = {
        item["path"]: item.get("project_family_id") for item in parsed
    }
    for symbol in symbols:
        symbols_by_file[symbol["file"]].append(symbol)
    for family in {s["project_family_id"] for s in symbols}: nodes.append({"id": family, "type": "project_family"})
    for record in audit.files:
        if record.extension in SUPPORTED: nodes.append({"id": stable_id("file", record.path), "type": "file", "path": record.path, "project_family_id": family_by_file.get(record.path)})
    for symbol in symbols:
        nodes.append(
            {
                "id": symbol["symbol_id"],
                "type": symbol["kind"],
                "name": symbol["name"],
                "file": symbol["file"],
                "project_family_id": symbol["project_family_id"],
                "stub": bool(symbol.get("stub")),
            }
        )
        edges.append(_edge(stable_id("file", symbol["file"]), symbol["symbol_id"], "defines", 1.0, "direct", "parser"))
    symbol_names = defaultdict(list)
    for symbol in symbols:
        symbol_names[
            (symbol["project_family_id"], symbol["name"])
        ].append(symbol)
    file_paths = {result["path"] for result in parsed}
    for result in parsed:
        source_file = stable_id("file", result["path"])
        for imported in result.get("imports", []):
            module_path = _resolve_module_path(result["path"], imported, file_paths)
            if module_path:
                edges.append(_edge(source_file, stable_id("file", module_path), "imports", .96, "resolved", "deterministic_module_resolution"))
        bindings = {item["local"]: item for item in result.get("import_bindings", [])}
        for ref in result.get("references", []):
            short = ref["target_name"].split(".")[-1]
            caller_name = ref.get("caller_name")
            caller = next((s for s in symbols_by_file[result["path"]] if caller_name and s["name"] == caller_name), None)
            if caller is None:
                callers = [s for s in symbols_by_file[result["path"]] if s["lines"]["start"] <= ref["line"] <= s["lines"]["end"]]
                caller = max(callers, key=lambda s: s["lines"]["start"]) if callers else None
            source = caller["symbol_id"] if caller else source_file
            targets = [s for s in symbols_by_file[result["path"]] if s["name"] == short]
            method, confidence, observation = ref["method"], ref["confidence"], "resolved"
            binding = bindings.get(ref["target_name"].split(".")[0])
            if not targets and binding:
                module_path = _resolve_module_path(result["path"], binding["source"], file_paths)
                imported_name = binding["imported"]
                candidates = [s for s in symbols_by_file.get(module_path or "", []) if s["name"] == imported_name or imported_name == "default" and s["exported"]]
                targets = candidates
                method, confidence = "import_binding_resolution", .96
            if not targets:
                targets = symbol_names.get(
                    (result.get("project_family_id"), short),
                    [],
                )
                if len(targets) == 1:
                    method, confidence, observation = "unique_family_symbol_heuristic", .58, "heuristic"
            if len(targets) == 1 and source != targets[0]["symbol_id"]:
                edge = _edge(source, targets[0]["symbol_id"], "calls", confidence, observation, method)
                edge["arguments"] = ref.get("argument_names", [])
                edge["target_parameters"] = targets[0].get("parameters", [])
                edges.append(edge)
                if edge["arguments"] and edge["target_parameters"]:
                    flow = _edge(source, targets[0]["symbol_id"], "passes_data", min(confidence, .9), observation, method)
                    flow["mapping"] = _argument_mapping(edge["arguments"], edge["target_parameters"])
                    edges.append(flow)
                lower = ref["target_name"].lower()
                if any(term in lower for term in (".save", ".create", ".insert", ".update", ".commit", ".delete")):
                    edges.append(_edge(source, targets[0]["symbol_id"], "writes_to", min(confidence, .85), observation, method))
                elif any(term in lower for term in (".find", ".get", ".read", ".select", ".query")):
                    edges.append(_edge(source, targets[0]["symbol_id"], "reads_from", min(confidence, .85), observation, method))
    for category, items in surfaces.items():
        if category in {"risk_indicators", "tests"}: continue
        for item in items:
            nodes.append({"id": item["surface_id"], "type": item["type"], "file": item["file"], "project_family_id": item.get("project_family_id"), "name": item.get("route") or item.get("name") or item.get("provider") or item.get("queue")})
            edges.append(_edge(stable_id("file", item["file"]), item["surface_id"], "contains", 1.0, "direct", "framework_pattern"))
            candidates = [s for s in symbols_by_file[item["file"]] if s["lines"]["start"] <= item.get("line", s["lines"]["start"]) <= s["lines"]["end"]]
            if candidates and item["type"] != "endpoint":
                owner = max(candidates, key=lambda s: s["lines"]["start"])
                edge_type = {"queue_producer": "produces", "queue_consumer": "consumes", "schema": "persists", "integration": "calls_external", "ui_action": "triggers"}.get(item["type"], "uses")
                edges.append(_edge(owner["symbol_id"], item["surface_id"], edge_type, .82, "direct", "same_symbol_body"))
            if item["type"] == "endpoint" and item.get("handler"):
                target = next((s for s in symbols if s["name"] == item["handler"] and s["project_family_id"] == item.get("project_family_id")), None)
                if target: edges.append(_edge(item["surface_id"], target["symbol_id"], "routes_to", .94, "direct", "framework_pattern"))
            if item["type"] == "queue_consumer" and item.get("handler"):
                target = next((s for s in symbols if s["name"] == item["handler"] and s["project_family_id"] == item.get("project_family_id")), None)
                if target: edges.append(_edge(item["surface_id"], target["symbol_id"], "invokes", .9, "resolved", "worker_callback"))
    for action in surfaces["ui"]:
        for endpoint in surfaces["endpoints"]:
            if action.get("project_family_id") == endpoint.get("project_family_id") and _route_match(action["target"], endpoint["route"]):
                edges.append(_edge(action["surface_id"], endpoint["surface_id"], "triggers", .92, "resolved", "route_match"))
    producers = [x for x in surfaces["async"] if x["type"] == "queue_producer"]
    consumers = [x for x in surfaces["async"] if x["type"] == "queue_consumer"]
    for producer in producers:
        for consumer in consumers:
            if producer.get("project_family_id") == consumer.get("project_family_id") and producer["queue"] == consumer["queue"] and producer["queue"] != "unknown":
                edges.append(_edge(producer["surface_id"], consumer["surface_id"], "consumed_by", .9, "resolved", "queue_name"))
    truncated = len(nodes) > limit
    nodes = sorted({n["id"]: n for n in nodes}.values(), key=lambda n: n["id"])[:limit]
    node_ids = {n["id"] for n in nodes}
    edges = sorted({(e["source"], e["target"], e["type"]): e for e in edges if e["source"] in node_ids and e["target"] in node_ids}.values(), key=lambda e: (e["source"], e["target"], e["type"]))
    data_flow = [edge for edge in edges if edge["type"] in {"passes_data", "reads_from", "writes_to"}]
    data_flow_truncated = len(data_flow) > max_data_flow_edges
    if data_flow_truncated:
        keep = {edge["edge_id"] for edge in data_flow[:max_data_flow_edges]}
        edges = [edge for edge in edges if edge["type"] not in {"passes_data", "reads_from", "writes_to"} or edge["edge_id"] in keep]
    return {"schema_version": "1.0", "nodes": nodes, "edges": edges, "truncated": truncated, "node_limit": limit, "data_flow_edge_limit": max_data_flow_edges, "data_flow_truncated": data_flow_truncated}


def _resolve_module_path(source_path, specifier, file_paths):
    if not specifier or not specifier.startswith("."):
        return None
    source = PurePosixPath(source_path)
    base = source.parent.joinpath(specifier)
    candidates = [base]
    for suffix in (".ts", ".tsx", ".js", ".jsx", ".py"):
        candidates.append(PurePosixPath(str(base) + suffix))
    for suffix in (".ts", ".tsx", ".js", ".jsx", ".py"):
        candidates.append(base / ("index" + suffix))
    normalized = {str(PurePosixPath(*_normalize_parts(candidate.parts))) for candidate in candidates}
    return next((path for path in sorted(normalized) if path in file_paths), None)


def _normalize_parts(parts):
    output = []
    for part in parts:
        if part in {"", "."}:
            continue
        if part == "..":
            if output:
                output.pop()
            continue
        output.append(part)
    return output


def _argument_mapping(arguments, parameters):
    return [{"argument": argument, "parameter": parameters[index] if index < len(parameters) else None} for index, argument in enumerate(arguments)]


def _workflows(graph, surfaces, depth):
    adjacency = defaultdict(list)
    for edge in graph["edges"]: adjacency[edge["source"]].append(edge)
    workflows = []
    entries = surfaces["ui"] + surfaces["endpoints"]
    for entry in entries:
        if entry["type"] == "endpoint" and any(
            ui.get("project_family_id") == entry.get("project_family_id")
            and _route_match(ui["target"], entry["route"])
            for ui in surfaces["ui"]
        ):
            continue
        seen, queue = {entry["surface_id"]}, deque([(entry["surface_id"], 0)])
        path_edges = []
        while queue:
            node, level = queue.popleft()
            if level >= depth: continue
            for edge in adjacency[node]:
                path_edges.append(edge)
                if edge["target"] not in seen:
                    seen.add(edge["target"]); queue.append((edge["target"], level + 1))
        node_map = {n["id"]: n for n in graph["nodes"]}
        visited = [node_map[node] for node in sorted(seen) if node in node_map]
        producers = [n for n in visited if n["type"] == "queue_producer"]
        consumers = [n for n in visited if n["type"] == "queue_consumer"]
        missing = []
        if producers and not consumers: missing.append("Queue producer exists, but no matching production consumer is connected.")
        endpoint = next((n for n in visited if n["type"] == "endpoint"), None)
        if not endpoint and entry["type"] == "ui_action": missing.append("UI action has no matched API endpoint.")
        implementation = [
            node
            for node in visited
            if node["type"] in {"function", "class"}
            and not node.get("stub")
            and not _is_test_path(str(node.get("file", "")))
        ]
        persistence = [
            node
            for node in visited
            if node["type"] == "schema"
            or re.search(
                r"save|create|insert|update|commit|persist|store|repository|database|prisma|session|db",
                str(node.get("name", "")),
                re.I,
            )
        ]
        outputs = [
            node
            for node in visited
            if re.search(
                r"report|export|pdf|result|emit|deliver|respond|render|serialize|output",
                str(node.get("name", "")),
                re.I,
            )
        ]
        has_persistence_edge = any(
            edge["type"] in {"persists", "writes_to"} for edge in path_edges
        )
        meaningful = bool(endpoint and implementation)
        database = bool(persistence or has_persistence_edge)
        report = bool(outputs)
        status = "verified_end_to_end" if meaningful and database and report and not missing else "partially_implemented" if len(visited) >= 2 else "interface_only"
        if entry["type"] == "endpoint" and not entry.get("registered", True): status, missing = "implemented_but_disconnected", missing + ["Route handler exists but no registration was verified."]
        workflows.append({"schema_version": "1.0", "workflow_id": stable_id("workflow", entry["surface_id"]), "project_family_id": entry.get("project_family_id"), "name": _workflow_name(entry), "actor": "user or external client", "trigger": entry.get("action") or f"{entry.get('method', '')} {entry.get('route', '')}".strip(), "entry_point": {"type": entry["type"], "reference": entry["surface_id"]}, "steps": [{"order": i + 1, "type": n["type"], "reference": n["id"], "name": n.get("name"), "file": n.get("file")} for i, n in enumerate(visited)], "branches": [], "data_stores": [n["id"] for n in visited if n["type"] == "schema"], "external_dependencies": [n["id"] for n in visited if n["type"] == "integration"], "outputs": ["observable output"] if report else [], "user_visible_result": report, "structural_evidence": {"implementation_symbols": [n["id"] for n in implementation], "persistence_sinks": [n["id"] for n in persistence], "output_sinks": [n["id"] for n in outputs]}, "authentication_state": "observed" if any(re.search(r"auth|login|jwt", str(n.get("name", "")), re.I) for n in visited) else "unknown", "failure_handling": "not fully verified", "tests": [], "missing_links": missing, "contradictions": [], "confidence": _confidence(status, len(path_edges), len(missing)), "confidence_label": _label(_confidence(status, len(path_edges), len(missing))), "completion_status": status, "supporting_graph_edges": path_edges})
    return sorted(workflows, key=lambda w: w["workflow_id"])


def _capabilities(audit, workflows, surfaces, symbols, reachability):
    specs = [
        ("authenticated-access", "Authenticated user access", r"login|signup|auth|jwt", "authentication"),
        ("document-ingestion", "Document or file ingestion", r"upload|import|ingest", "ingestion"),
        ("rule-evaluation", "Rule-based evaluation", r"evaluate|evaluator|rule|score|finding", "evaluation"),
        ("report-generation", "Report generation and delivery", r"report|pdf|export|result", "reporting"),
        ("background-processing", "Background task processing", r"queue|worker|job|task", "workflow"),
        ("subscription-billing", "Subscription billing", r"stripe|checkout|subscription|invoice", "billing"),
        ("data-persistence", "Persistent data storage", r"save|create|insert|update|commit|persist|store|repository|prisma|session|database|model", "data"),
    ]
    capabilities = []
    production_symbols = [s for s in symbols if not _is_test_path(s["file"])]
    test_symbols = [s for s in symbols if _is_test_path(s["file"])]
    workflow_target_ids = {
        edge["target"]
        for workflow in workflows
        for edge in workflow["supporting_graph_edges"]
    }
    for key, name, pattern, category in specs:
        matched = [s for s in production_symbols if re.search(pattern, s["name"] + " " + s["qualified_name"], re.I)]
        substantive = [s for s in matched if not s.get("stub")]
        test_match = [s for s in test_symbols if re.search(pattern, s["name"] + " " + s["qualified_name"], re.I)]
        matched_ids = {s["symbol_id"] for s in matched}
        related_workflows = [
            w for w in workflows
            if any(step["reference"] in matched_ids for step in w["steps"])
            or re.search(pattern, w["name"], re.I)
        ]
        integration = [i for i in surfaces["integrations"] if re.search(pattern, i["provider"], re.I)]
        schema = [s for s in surfaces["schemas"] if re.search(pattern, s["name"], re.I)]
        if not matched and not test_match and not integration and not schema: continue
        status = "inferred"
        missing = []
        verified = [w for w in related_workflows if w["completion_status"] == "verified_end_to_end"]
        partial = [w for w in related_workflows if w["completion_status"] in {"partially_implemented", "implemented_but_disconnected"}]
        if matched and not substantive: status = "interface_only"
        elif verified: status = "verified_end_to_end"
        elif partial and matched: status = "implemented_but_disconnected" if any(w["completion_status"] == "implemented_but_disconnected" for w in partial) else "partially_implemented"
        elif substantive:
            referenced = any(
                item["symbol_id"] in workflow_target_ids
                for item in reachability
                if item["symbol_id"] in matched_ids
            )
            status = "implemented_but_disconnected" if not referenced else "partially_implemented"
        elif schema: status = "schema_only"
        elif integration: status = "configuration_only" if all(i["usage"] == "configuration_only" for i in integration) else "partially_implemented"
        elif test_match: status = "test_or_mock_only"
        if status != "verified_end_to_end": missing.append("No verified connected path from product trigger to meaningful output.")
        score = {"verified_end_to_end": .92, "implemented_but_disconnected": .72, "partially_implemented": .62, "interface_only": .34, "schema_only": .38, "configuration_only": .3, "test_or_mock_only": .28, "inferred": .22}.get(status, .2)
        workflow_paths = {
            step["file"]
            for workflow in related_workflows
            for step in workflow["steps"]
            if step.get("file")
        }
        project_family_ids = {
            item["project_family_id"]
            for item in matched + test_match + integration + schema
            if item.get("project_family_id")
        } | {
            workflow["project_family_id"]
            for workflow in related_workflows
            if workflow.get("project_family_id")
        }
        capabilities.append({"schema_version": "1.0", "capability_id": stable_id("capability", key), "key": key, "name": name, "category": category, "status": status, "confidence": score, "confidence_label": _label(score), "evidence_strength": _evidence_strength(score), "score_components": {"parser_certainty": .85, "direct_relationships": .85 if verified else .5, "reachability": .9 if verified else .45, "test_strength": .55 if test_match else .2, "contradiction_penalty": 0}, "project_family_ids": sorted(project_family_ids), "supporting_workflow_ids": [w["workflow_id"] for w in related_workflows], "supporting_symbols": [s["symbol_id"] for s in matched], "supporting_paths": sorted({s["file"] for s in matched} | workflow_paths), "contradictory_evidence": [], "missing_components": missing, "test_evidence": {"strength": "moderate" if test_match else "none", "notes": "Tests are structural evidence only; they were not executed."}, "reachability": "production_referenced" if verified else "unverified_or_disconnected", "deployment_evidence": "not dynamically verified", "security_concerns": ["Review authentication, authorization, validation, secret handling, and tenant boundaries."], "extraction_readiness": "high" if verified else "moderate" if matched else "low", "reusability": "high" if matched else "unknown", "coupling": "moderate", "explanation": _capability_explanation(name, status)})

    # Structure establishes that substantive capability exists. Vocabulary only
    # names it. Never silently omit a project merely because its domain verbs
    # are absent from the built-in labels.
    named_families = {
        family_id
        for capability in capabilities
        if capability["key"] != "data-persistence"
        for family_id in capability["project_family_ids"]
    }
    symbols_by_family = defaultdict(list)
    for symbol in production_symbols:
        if not symbol.get("stub"):
            symbols_by_family[symbol["project_family_id"]].append(symbol)
    workflows_by_family = defaultdict(list)
    for workflow in workflows:
        if workflow.get("project_family_id"):
            workflows_by_family[workflow["project_family_id"]].append(workflow)
    for family_id, family_symbols in sorted(symbols_by_family.items()):
        if family_id in named_families or len(family_symbols) < 3:
            continue
        family_workflows = workflows_by_family.get(family_id, [])
        structural = [
            workflow
            for workflow in family_workflows
            if workflow.get("structural_evidence", {}).get("implementation_symbols")
        ]
        verified = [
            workflow
            for workflow in structural
            if workflow["completion_status"] == "verified_end_to_end"
        ]
        status = "verified_end_to_end" if verified else "implemented_but_disconnected"
        score = .82 if verified else .55
        key = f"unclassified-capability:{family_id}"
        supporting_workflows = verified or structural
        capabilities.append(
            {
                "schema_version": "1.0",
                "capability_id": stable_id("capability", key),
                "key": key,
                "name": "Unclassified substantive capability",
                "category": "unclassified",
                "status": status,
                "confidence": score,
                "confidence_label": _label(score),
                "evidence_strength": _evidence_strength(score),
                "score_components": {
                    "parser_certainty": .85,
                    "direct_relationships": .85 if verified else .5,
                    "reachability": .9 if verified else .45,
                    "test_strength": .2,
                    "contradiction_penalty": 0,
                },
                "project_family_ids": [family_id],
                "supporting_workflow_ids": [
                    workflow["workflow_id"] for workflow in supporting_workflows
                ],
                "supporting_symbols": [
                    symbol["symbol_id"] for symbol in family_symbols
                ],
                "supporting_paths": sorted(
                    {symbol["file"] for symbol in family_symbols}
                ),
                "contradictory_evidence": [],
                "missing_components": []
                if verified
                else ["No verified connected path from product trigger to meaningful output."],
                "test_evidence": {
                    "strength": "none",
                    "notes": "Tests are structural evidence only; they were not executed.",
                },
                "reachability": "production_referenced"
                if verified
                else "unverified_or_disconnected",
                "deployment_evidence": "not dynamically verified",
                "security_concerns": [
                    "Review authentication, authorization, validation, secret handling, and tenant boundaries."
                ],
                "extraction_readiness": "high" if verified else "moderate",
                "reusability": "unknown",
                "coupling": "moderate",
                "explanation": (
                    "A substantive production structure was found, but the current "
                    "vocabulary cannot assign a defensible domain label. Review the "
                    "supporting workflow and symbols instead of treating this project "
                    "as capability-free."
                ),
            }
        )
    return sorted(capabilities, key=lambda c: c["capability_id"])


def _contradictions(audit, capabilities, surfaces, parse_results, family_for):
    contradictions = []
    claims = [("compliance", "rule-evaluation"), ("report", "report-generation"), ("billing", "subscription-billing"), ("monitor", "background-processing"), ("automat", "background-processing")]
    by_key = {c["key"]: c for c in capabilities}
    family_coverage = _coverage_snapshot(parse_results)["project_families"]
    docs_by_family = defaultdict(list)
    for record in audit.files:
        if record.role == "documentation" and record.text:
            docs_by_family[family_for(record.path)].append(record)
    for family_id, records in sorted(docs_by_family.items()):
        gate = family_coverage.get(family_id, {})
        if gate.get("conclusion_status") != "eligible":
            continue
        docs = "\n".join(record.text or "" for record in records)
        for term, key in claims:
            if not re.search(term, docs, re.I):
                continue
            cap = by_key.get(key)
            cap_in_family = bool(
                cap and family_id in cap.get("project_family_ids", [])
            )
            if cap_in_family and cap["status"] == "verified_end_to_end":
                continue
            technical_finding = (
                cap["explanation"]
                if cap_in_family
                else "No substantive implementation was found in the same project family."
            )
            contradictions.append({"contradiction_id": stable_id("contradiction", family_id, term, key), "project_family_id": family_id, "claim": f"Documentation claims {term}-related behavior.", "technical_finding": technical_finding, "capability_id": cap["capability_id"] if cap_in_family else None, "severity": "material", "confidence": .86, "evidence_strength": "strong", "evidence": [record.path for record in records if re.search(term, record.text or "", re.I)]})
    for ui in surfaces["ui"] + surfaces.get("ui_screens", []):
        if ui["mock_only"]:
            contradictions.append({"contradiction_id": stable_id("contradiction", ui["surface_id"]), "project_family_id": ui.get("project_family_id"), "claim": "A user-visible surface presents result data.", "technical_finding": "The surface contains mock or fixture data.", "capability_id": None, "severity": "material", "confidence": .9, "evidence_strength": "strong", "evidence": [ui["file"]]})
    return sorted(contradictions, key=lambda c: c["contradiction_id"])


def _apply_contradictions(capabilities, contradictions):
    for cap in capabilities:
        related = [c for c in contradictions if c["capability_id"] == cap["capability_id"]]
        if related:
            cap["contradictory_evidence"] = [c["contradiction_id"] for c in related]
            cap["score_components"]["contradiction_penalty"] = .15
            cap["confidence"] = max(.05, round(cap["confidence"] - .15, 2))
            cap["confidence_label"] = _label(cap["confidence"])
            cap["evidence_strength"] = _evidence_strength(cap["confidence"])
            if cap["status"] in {"inferred", "configuration_only", "test_or_mock_only"}: cap["status"] = "contradicted"


def _reachability(symbols, graph, audit):
    nodes = {n["id"]: n for n in graph["nodes"]}
    reference_types = {"imports", "calls", "routes_to", "invokes", "triggers", "produces", "consumes", "consumed_by", "persists", "calls_external"}
    incoming = Counter(e["target"] for e in graph["edges"] if e["type"] in reference_types)
    production_incoming = Counter(
        e["target"] for e in graph["edges"]
        if e["type"] in reference_types
        and not _is_test_path(str(nodes.get(e["source"], {}).get("file", "")))
    )
    results = []
    for symbol in symbols:
        test = _is_test_path(symbol["file"])
        count = incoming[symbol["symbol_id"]]
        state = "test_only" if test or (count and not production_incoming[symbol["symbol_id"]]) else "verified_referenced" if production_incoming[symbol["symbol_id"]] else "unreferenced" if symbol["exported"] else "unknown"
        results.append({"symbol_id": symbol["symbol_id"], "file": symbol["file"], "name": symbol["name"], "status": state, "incoming_edges": count, "confidence": .9 if count or test else .65})
    return sorted(results, key=lambda r: r["symbol_id"])


def _summary(audit, parsed, symbols, graph, families, workflows, capabilities, contradictions, surfaces):
    statuses = Counter(item["status"] for item in parsed)
    verified_wf = sum(w["completion_status"] == "verified_end_to_end" for w in workflows)
    verified_cap = sum(c["status"] == "verified_end_to_end" for c in capabilities)
    coverage = _coverage_snapshot(parsed)
    scan_id = hashlib.sha256("\n".join(f"{r.path}:{r.sha256}" for r in audit.files if r.sha256).encode()).hexdigest()[:16]
    return {
        "schema_version": "1.0",
        "engine_version": "0.4.1",
        "analysis_status": "complete"
        if coverage["conclusion_status"] == "eligible"
        else "partial",
        "conclusion_gate": {
            "status": coverage["conclusion_status"],
            "minimum_coverage": MIN_CONCLUSION_COVERAGE,
            "blocking_reasons": coverage["blocking_reasons"],
            "negative_conclusions_allowed": coverage["conclusion_status"] == "eligible",
        },
        "scan_id": scan_id,
        "project_family_count": len(families),
        "files_considered": coverage["considered_files"],
        "files_parsed": statuses["success"],
        "files_partially_parsed": statuses["partial"],
        "files_unsupported": statuses["unsupported"],
        "parser_failures": statuses["parser_failure"],
        "symbols_detected": len(symbols),
        "relationships_detected": len(graph["edges"]),
        "workflows_detected": len(workflows),
        "verified_workflows": verified_wf,
        "partial_workflows": sum(
            workflow["completion_status"] != "verified_end_to_end" for workflow in workflows
        ),
        "capabilities_detected": len(capabilities),
        "verified_capabilities": verified_cap,
        "contradictions_detected": len(contradictions),
        "coverage": {
            **coverage,
            "frameworks": sorted(
                {item["name"] for item in surfaces.get("frameworks", [])}
            ),
        },
        "limitations": [
            "JavaScript and TypeScript use a deterministic in-process token AST, not a full compiler type checker.",
            "Dynamic dispatch, reflection, generated code, dependency injection, and cross-language calls can remain unresolved.",
            "Static reachability is evidence, not proof of runtime behavior.",
            "Persistent cache accelerates unchanged parsing but does not make dynamic behavior observable.",
        ],
        "safety": {
            "source_executed": False,
            "source_modified": False,
            "external_upload_performed": False,
        },
        "graph_truncated": graph["truncated"],
        "data_flow_truncated": graph["data_flow_truncated"],
    }


def _coverage_snapshot(parsed):
    def summarize(items):
        statuses = Counter(item["status"] for item in items)
        considered = [
            item for item in items if item["status"] != "excluded_test"
        ]
        supported = sum(
            item["status"] in {"success", "partial"} for item in considered
        )
        ratio = round(supported / len(considered), 4) if considered else 0.0
        blocking_counts = {
            status: statuses[status]
            for status in (
                "parser_failure",
                "invalid_syntax",
                "too_large",
                "binary_or_unreadable",
                "unsupported",
            )
            if statuses[status]
        }
        reasons = []
        if not considered:
            reasons.append("no_supported_source_evidence")
        if ratio < MIN_CONCLUSION_COVERAGE:
            reasons.append("coverage_below_threshold")
        if blocking_counts:
            reasons.append("unparsed_or_unsupported_source")
        return {
            "supported_files": supported,
            "considered_files": len(considered),
            "ratio": ratio,
            "parser_failures": statuses["parser_failure"],
            "blocking_status_counts": blocking_counts,
            "blocking_reasons": reasons,
            "conclusion_status": "insufficient_evidence"
            if reasons
            else "eligible",
        }

    project_families = {}
    by_family = defaultdict(list)
    for item in parsed:
        by_family[item.get("project_family_id") or stable_id("family", ".")].append(item)
    for family_id, items in sorted(by_family.items()):
        project_families[family_id] = summarize(items)
    overall = summarize(parsed)
    overall["languages"] = dict(
        sorted(Counter(item["language"] for item in parsed).items())
    )
    overall["project_families"] = project_families
    return overall


def _endpoint(path, family, method, route, handler, framework, registered, text):
    return {"surface_id": stable_id("endpoint", family, path, method.upper(), route), "project_family_id": family, "type": "endpoint", "file": path, "method": method.upper(), "route": route, "handler": handler, "framework": framework, "registered": registered, "validation": bool(re.search(r"schema|validate|pydantic|zod", text, re.I)), "authentication": bool(re.search(r"auth|user|jwt|Depends", text, re.I)), "authorization": bool(re.search(r"role|permission|authorize", text, re.I)), "error_handling": bool(re.search(r"try\s*[:{]|except|catch\s*\(", text)), "confidence": .94}


def _router_registered(audit, route_file):
    stem = PurePosixPath(route_file).stem
    root = _project_root_for_path(audit, route_file)
    return any(
        _project_root_for_path(audit, record.path) == root
        and record.text
        and re.search(
            rf"(include_router|use)\s*\([^)]*{re.escape(stem)}",
            record.text,
        )
        for record in audit.files
    )


def _project_root_for_path(audit, path):
    roots = [
        project.root
        for project in audit.projects
        if project.root == "." or path.startswith(project.root + "/")
    ]
    return max(roots, key=len, default=".")


def _next_symbol(symbols, line):
    candidates = [s for s in symbols if s["lines"]["start"] >= line]
    return min(candidates, key=lambda s: s["lines"]["start"])["name"] if candidates else None


def _risk_indicators(path, text):
    indicators = []
    checks = [("hard-coded-secret", r"\b(?:api[_-]?key|secret|password)\s*[:=]\s*['\"][^'\"]+"), ("subprocess", r"\b(?:subprocess\.|child_process\.|os\.system)"), ("dynamic-code", r"\b(?:eval|exec|new\s+Function)\s*\("), ("unsafe-upload", r"\b(?:upload|multipart)\b")]
    for name, pattern in checks:
        match = re.search(pattern, text, re.I)
        if match: indicators.append({"risk_id": stable_id("risk", path, name), "path": path, "line": _line(text, match.start()), "indicator": name, "conclusion": "structural_risk_indicator", "confidence": .8})
    return indicators


def _edge(source, target, kind, confidence, observation, method):
    return {"edge_id": stable_id("edge", source, target, kind), "source": source, "target": target, "type": kind, "confidence": confidence, "observation_type": observation, "extraction_method": method}


def _route_match(client, route):
    clean = client.split("?")[0].replace("${", ":")
    return clean == route or clean.endswith(route) or route.endswith(clean)
def _workflow_name(entry): return f"{entry.get('method', 'UI')} {entry.get('route') or entry.get('target') or entry.get('action')}"
def _confidence(status, edges, missing): return round(max(.15, min(.96, {"verified_end_to_end": .82, "partially_implemented": .58, "implemented_but_disconnected": .65, "interface_only": .35}.get(status, .3) + min(.1, edges * .015) - min(.2, missing * .08))), 2)
def _label(score): return "very high" if score >= .9 else "high" if score >= .75 else "moderate" if score >= .55 else "low" if score >= .3 else "very low"
def _evidence_strength(score): return "strong" if score >= .75 else "moderate" if score >= .55 else "weak"
def _capability_explanation(name, status): return f"{name} is classified as {status.replace('_', ' ')} based on static production-path evidence; scanned code was not executed."
def _is_test_path(path): return bool(re.search(r"(^|/)(tests?|fixtures?|mocks?)(/|$)|(?:test|spec)\.", path, re.I))
def _line(text, offset): return text.count("\n", 0, offset) + 1
def _dedupe(items): return sorted({item.get("surface_id") or item.get("risk_id"): item for item in items}.values(), key=lambda item: item.get("surface_id") or item.get("risk_id"))
