from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

import tree_sitter_python
from tree_sitter import Language, Parser

from backend.app.domain.model import (
    CallSite,
    Declaration,
    Edge,
    EdgeKind,
    Evidence,
    FileAnalysis,
    ImportFact,
    ImportKind,
    InheritanceSite,
    NodeKind,
    SourceSpan,
    stable_logical_id,
)


PY_LANGUAGE = Language(tree_sitter_python.language())


@dataclass
class Scope:
    name: str
    logical_id: str
    kind: NodeKind


class PythonParser:
    language = "python"

    def __init__(self) -> None:
        self._parser = Parser(PY_LANGUAGE)

    def parse_file(self, root: Path, path: Path) -> FileAnalysis:
        rel_path = path.relative_to(root).as_posix()
        source = path.read_bytes()
        tree = self._parser.parse(source)
        analysis = FileAnalysis(
            path=rel_path,
            language=self.language,
            file_hash=sha256(source).hexdigest(),
        )
        if tree.root_node.has_error:
            analysis.diagnostics.append("parse_error")

        file_id = stable_logical_id(rel_path, NodeKind.FILE, rel_path)
        for child in tree.root_node.children:
            self._walk_node(child, source, rel_path, [Scope(rel_path, file_id, NodeKind.FILE)], analysis)
        return analysis

    def _walk_node(
        self,
        node,
        source: bytes,
        rel_path: str,
        scopes: list[Scope],
        analysis: FileAnalysis,
    ) -> None:
        if node.type in {"function_definition", "class_definition"}:
            scope = self._handle_declaration(node, source, rel_path, scopes, analysis)
            for child in node.children:
                self._walk_node(child, source, rel_path, [*scopes, scope], analysis)
            return

        if node.type in {"import_statement", "import_from_statement"}:
            fact = self._extract_import(node, source, rel_path)
            if fact:
                analysis.imports.append(fact)

        if node.type == "call":
            analysis.call_sites.append(self._extract_call(node, source, rel_path, scopes))

        for child in node.children:
            self._walk_node(child, source, rel_path, scopes, analysis)

    def _handle_declaration(
        self,
        node,
        source: bytes,
        rel_path: str,
        scopes: list[Scope],
        analysis: FileAnalysis,
    ) -> Scope:
        name_node = node.child_by_field_name("name")
        name = self._text(source, name_node)
        parent = scopes[-1]
        qn_parts = [s.name for s in scopes[1:]] + [name]
        qualified_name = ".".join(qn_parts)
        kind = NodeKind.CLASS if node.type == "class_definition" else (
            NodeKind.METHOD if parent.kind == NodeKind.CLASS else NodeKind.FUNCTION
        )
        signature = self._signature(node, source) if kind in {NodeKind.FUNCTION, NodeKind.METHOD} else ""
        logical_id = stable_logical_id(rel_path, kind, qualified_name, signature)
        decl = Declaration(
            path=rel_path,
            kind=kind,
            name=name,
            qualified_name=qualified_name,
            signature=signature,
            enclosing_scope=parent.logical_id,
            span=SourceSpan.from_node(node),
            logical_id=logical_id,
        )
        analysis.declarations.append(decl)
        analysis.contains_edges.append(
            Edge(
                kind=EdgeKind.CONTAINS,
                source_id=parent.logical_id,
                target_id=logical_id,
                evidence=Evidence(rel_path, SourceSpan.from_node(node), "python.declaration_parent"),
            )
        )
        if kind == NodeKind.CLASS:
            superclasses = node.child_by_field_name("superclasses")
            if superclasses:
                for ident in self._identifier_texts(superclasses, source):
                    analysis.inheritance_sites.append(
                        InheritanceSite(rel_path, logical_id, ident, SourceSpan.from_node(superclasses))
                    )
        return Scope(name, logical_id, kind)

    def _extract_import(self, node, source: bytes, rel_path: str) -> ImportFact | None:
        raw = self._text(source, node)
        if node.type == "import_statement":
            dotted = node.named_children[0] if node.named_children else None
            if not dotted:
                return None
            module, alias = self._aliased_name(dotted, source)
            return ImportFact(rel_path, ImportKind.IMPORT, module, None, alias, 0, SourceSpan.from_node(node), raw)

        module_node = node.child_by_field_name("module_name")
        name_node = node.child_by_field_name("name")
        module = self._text(source, module_node) if module_node else ""
        name, alias = self._aliased_name(name_node, source) if name_node else (None, None)
        level = raw.split("import", 1)[0].count(".")
        return ImportFact(rel_path, ImportKind.FROM_IMPORT, module, name, alias, level, SourceSpan.from_node(node), raw)

    def _extract_call(self, node, source: bytes, rel_path: str, scopes: list[Scope]) -> CallSite:
        function_node = node.child_by_field_name("function")
        expression = self._text(source, function_node)
        receiver = None
        function_name = expression
        if function_node and function_node.type == "attribute":
            object_node = function_node.child_by_field_name("object")
            attr_node = function_node.child_by_field_name("attribute")
            receiver = self._text(source, object_node)
            function_name = self._text(source, attr_node)
        return CallSite(rel_path, scopes[-1].logical_id if len(scopes) > 1 else None, expression, function_name, receiver, SourceSpan.from_node(node))

    def _signature(self, node, source: bytes) -> str:
        params = node.child_by_field_name("parameters")
        return self._text(source, params) if params else "()"

    def _aliased_name(self, node, source: bytes) -> tuple[str, str | None]:
        text = self._text(source, node)
        if " as " in text:
            left, right = text.split(" as ", 1)
            return left.strip(), right.strip()
        return text.strip(), None

    def _identifier_texts(self, node, source: bytes) -> list[str]:
        found: list[str] = []
        stack = list(node.named_children)
        while stack:
            current = stack.pop(0)
            if current.type in {"identifier", "dotted_name"}:
                found.append(self._text(source, current))
            else:
                stack.extend(current.named_children)
        return found

    def _text(self, source: bytes, node) -> str:
        if node is None:
            return ""
        return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")
