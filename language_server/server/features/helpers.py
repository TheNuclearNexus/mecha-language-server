import logging
from typing import Any, Iterable, cast

from beet import NamespaceFile
from bolt import AstIdentifier, AstTargetIdentifier, Binding, LexicalScope
from lsprotocol import types as lsp
from mecha import AstNode, AstResourceLocation
from tokenstream import SourceLocation

from ..indexing import ProjectIndex

from .. import MechaLanguageServer
from .validate import get_compilation_data


def get_representation_file(project_index: ProjectIndex, node: AstResourceLocation):
    if not (represents := cast(type[NamespaceFile]|str|None, node.__dict__.get("represents"))):
            return None
        
    if isinstance(represents, str):
        return None
        
    return represents


def node_location_to_range(node: AstNode | Iterable[SourceLocation]):
    if isinstance(node, AstNode):
        location = node.location
        end_location = node.end_location
    else:
        location, end_location = node

    return lsp.Range(
        start=location_to_position(location), end=location_to_position(end_location)
    )


def node_start_to_range(node: AstNode):
    start = location_to_position(node.location)
    end = lsp.Position(line=start.line, character=start.character + 1)

    return lsp.Range(start=start, end=end)


def location_to_position(location: SourceLocation) -> lsp.Position:
    return lsp.Position(
        line=max(location.lineno - 1, 0),
        character=max(location.colno - 1, 0),
    )


def fetch_compilation_data(ls: MechaLanguageServer, params: Any):
    text_doc = ls.workspace.get_document(params.text_document.uri)
    with ls.context(text_doc) as ctx:

        if ctx is None:
            return None

        compiled_doc = get_compilation_data(ctx, text_doc)
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
