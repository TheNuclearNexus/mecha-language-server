import logging
from typing import Any

from bolt import AstIdentifier, AstTargetIdentifier, Binding, LexicalScope
from lsprotocol import types as lsp
from mecha import AstNode
from tokenstream import SourceLocation

from .. import MechaLanguageServer
from .validate import get_compilation_data


def node_location_to_range(node: AstNode):
    return lsp.Range(
        start=lsp.Position(
            line=node.location.lineno - 1, character=node.location.colno - 1
        ),
        end=lsp.Position(
            line=node.end_location.lineno - 1, character=node.end_location.colno - 1
        ),
    )


def node_start_to_range(node: AstNode):
    start = lsp.Position(
        line=node.location.lineno - 1, character=node.location.colno - 1
    )
    end = lsp.Position(line=start.line, character=start.character + 1)

    return lsp.Range(start=start, end=end)


def fetch_compilation_data(ls: MechaLanguageServer, params: Any):
    text_doc = ls.workspace.get_document(params.text_document.uri)
    ctx = ls.get_context(text_doc)

    if ctx is None:
        return None

    compiled_doc = get_compilation_data(ls, ctx, text_doc)
    return compiled_doc


def get_node_at_position(root: AstNode, pos: lsp.Position):
    target = SourceLocation(0, pos.line + 1, pos.character + 1)
    nearest_node = root
    for node in root.walk():
        start = node.location
        end = node.end_location

        if not (start.colno <= target.colno and end.colno >= target.colno):
            continue

        if not (start.lineno == target.lineno and end.lineno == target.lineno):
            continue

        if (
            start.pos >= nearest_node.location.pos
            and end.pos <= nearest_node.end_location.pos
        ):
            nearest_node = node

    return nearest_node


def offset_location(location: SourceLocation, offset):
    return SourceLocation(
        location.pos + offset, location.lineno, location.colno + offset
    )


def search_scope_for_binding(
    var_name: str, node: AstIdentifier | AstTargetIdentifier, scope: LexicalScope
) -> tuple[Binding, LexicalScope] | None:
    variables = scope.variables

    if var_name in variables:
        var_data = variables[var_name]

        for binding in var_data.bindings:
            if node in binding.references or node == binding.origin:
                return (binding, scope)

    for child in scope.children:
        if binding := search_scope_for_binding(var_name, node, child):
            return binding

    return None
