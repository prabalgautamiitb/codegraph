from pathlib import Path

from backend.app.domain.model import EdgeKind, NodeKind
from backend.app.ingestion.analyze import analyze_repository


FIXTURE = Path("fixtures/python_demo")


def test_python_demo_extracts_declarations_and_diagnostics():
    result = analyze_repository(FIXTURE)

    names = {decl.qualified_name for file in result.files for decl in file.declarations}

    assert "BaseService" in names
    assert "BaseService.audit" in names
    assert "OrderService" in names
    assert "OrderService.submit" in names
    assert "validate" in names
    assert "store" in names
    assert "place_order" in names
    assert "place_order.submit" in names
    assert result.counts["parse_errors"] == 1
    assert result.counts["supported"] == 5
    assert result.counts["unsupported"] == 0


def test_contains_edges_and_spans_are_source_backed():
    result = analyze_repository(FIXTURE)
    contains = [
        edge
        for edge in result.edges
        if edge.kind == EdgeKind.CONTAINS and edge.evidence.path.endswith(".py")
    ]

    assert contains
    assert all(edge.evidence.path.endswith(".py") for edge in contains)
    assert all(edge.evidence.span.start_line >= 1 for edge in contains)


def test_conservative_calls_do_not_resolve_unknown_receiver():
    result = analyze_repository(FIXTURE)
    call_edges = [edge for edge in result.edges if edge.kind == EdgeKind.CALLS]
    unresolved = {(ref.expression, ref.reason) for ref in result.unresolved_references}

    assert any(edge.evidence.rule == "python.direct_call" for edge in call_edges)
    assert ("svc.submit", "unknown_receiver") in unresolved
    assert ("imported_store", "unknown_name") not in unresolved


def test_inheritance_and_import_edges_are_explicit():
    result = analyze_repository(FIXTURE)

    assert any(edge.kind == EdgeKind.INHERITS for edge in result.edges)
    assert any(edge.kind == EdgeKind.IMPORTS for edge in result.edges)


def test_markdown_references_and_pyproject_dependencies_are_extracted():
    result = analyze_repository(FIXTURE)
    declarations = [decl for file in result.files for decl in file.declarations]
    dependency_names = {decl.name for decl in declarations if decl.kind == NodeKind.DEPENDENCY}

    assert {"fastapi", "requests", "pytest"}.issubset(dependency_names)
    assert any(decl.kind == NodeKind.DOCUMENT and decl.path == "README.md" for decl in declarations)
    assert any(edge.kind == EdgeKind.REFERENCES for edge in result.edges)
    assert any(edge.kind == EdgeKind.DECLARES_DEPENDENCY for edge in result.edges)
