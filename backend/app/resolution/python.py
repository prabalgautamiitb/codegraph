from __future__ import annotations

from pathlib import Path

from backend.app.domain.model import (
    Edge,
    EdgeKind,
    Evidence,
    FileAnalysis,
    ImportKind,
    NodeKind,
    RepositoryAnalysis,
    UnresolvedReference,
    stable_logical_id,
)


def resolve_python(root: Path, files: list[FileAnalysis], counts: dict[str, int]) -> RepositoryAnalysis:
    declarations = [decl for file in files for decl in file.declarations]
    by_qn = {decl.qualified_name: decl for decl in declarations}
    by_module_member: dict[tuple[str, str], object] = {}
    module_files = {Path(file.path).with_suffix("").as_posix().replace("/", "."): file for file in files}
    file_ids = {file.path: stable_logical_id(file.path, NodeKind.FILE, file.path) for file in files}

    for decl in declarations:
        module = Path(decl.path).with_suffix("").as_posix().replace("/", ".")
        by_module_member[(module, decl.name)] = decl

    edges: list[Edge] = []
    unresolved: list[UnresolvedReference] = []
    for file in files:
        edges.extend(file.contains_edges)
        imports_by_binding = {}
        for imp in file.imports:
            target_file = module_files.get(_resolve_module(file.path, imp.module, imp.level))
            if target_file:
                edges.append(Edge(EdgeKind.IMPORTS, file_ids[file.path], file_ids[target_file.path], Evidence(file.path, imp.span, "python.import_module")))
            elif imp.name:
                target = by_module_member.get((_resolve_module(file.path, imp.module, imp.level), imp.name))
                if target:
                    imports_by_binding[imp.binding_name] = target
                    edges.append(Edge(EdgeKind.IMPORTS, file_ids[file.path], target.logical_id, Evidence(file.path, imp.span, "python.from_import_symbol")))
                else:
                    unresolved.append(UnresolvedReference(file.path, "import", imp.raw, "unknown_import", imp.span))
            else:
                unresolved.append(UnresolvedReference(file.path, "import", imp.raw, "external_or_unknown_module", imp.span))
            if imp.name:
                maybe = by_module_member.get((_resolve_module(file.path, imp.module, imp.level), imp.name))
                if maybe:
                    imports_by_binding[imp.binding_name] = maybe

        local_functions = {decl.name: decl for decl in file.declarations if decl.kind in {NodeKind.FUNCTION, NodeKind.METHOD}}
        for call in file.call_sites:
            target = None
            reason = ""
            if call.receiver:
                reason = "unknown_receiver"
            elif call.function_name in local_functions:
                target = local_functions[call.function_name]
            elif call.function_name in imports_by_binding:
                target = imports_by_binding[call.function_name]
            else:
                reason = "unknown_name"
            if target and call.caller_logical_id:
                edges.append(Edge(EdgeKind.CALLS, call.caller_logical_id, target.logical_id, Evidence(call.path, call.span, "python.direct_call")))
            else:
                unresolved.append(UnresolvedReference(call.path, "call", call.expression, reason or "top_level_call", call.span))

        for inherit in file.inheritance_sites:
            target = by_qn.get(inherit.parent_name) or next((d for d in declarations if d.kind == NodeKind.CLASS and d.name == inherit.parent_name), None)
            if target:
                edges.append(Edge(EdgeKind.INHERITS, inherit.subclass_logical_id, target.logical_id, Evidence(inherit.path, inherit.span, "python.explicit_base")))
            else:
                unresolved.append(UnresolvedReference(inherit.path, "inheritance", inherit.parent_name, "unknown_parent", inherit.span))

    counts = {**counts}
    counts["parse_errors"] = sum(1 for file in files if file.diagnostics)
    counts["declarations"] = len(declarations)
    counts["edges"] = len(edges)
    counts["unresolved"] = len(unresolved)
    return RepositoryAnalysis(str(root), "0.1.0", files, edges, unresolved, counts)


def _resolve_module(file_path: str, module: str, level: int) -> str:
    if level == 0:
        return module
    package = Path(file_path).parent.parts
    keep = max(0, len(package) - level + 1)
    prefix = ".".join(package[:keep])
    return ".".join(part for part in [prefix, module] if part)
