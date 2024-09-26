import logging
from bolt import AstIdentifier, AstTargetIdentifier, LexicalScope
from lsprotocol import types as lsp

from .validate import get_compilation_data

from .helpers import (
    fetch_compilation_data,
    get_node_at_position,
    node_location_to_range,
    node_start_to_range,
)

from .. import MechaLanguageServer


def search_scope(
    var_name: str, node: AstIdentifier | AstTargetIdentifier, scope: LexicalScope
) -> lsp.Range | None:
    variables = scope.variables
   
    if var_name in variables:
        var_data = variables[var_name]

        for binding in var_data.bindings:
            if node in binding.references or node == binding.origin:
                return node_start_to_range(binding.origin)

    for child in scope.children:
        if range := search_scope(var_name, node, child):
            return range

    return None


def get_definition(ls: MechaLanguageServer, params: lsp.DefinitionParams):
    compiled_doc = fetch_compilation_data(ls, params)

    if compiled_doc is None or compiled_doc.compiled_module is None:
        return []

    ast = compiled_doc.compiled_module.ast
    scope = compiled_doc.compiled_module.lexical_scope

    node = get_node_at_position(ast, params.position)
    if isinstance(node, AstIdentifier) or isinstance(node, AstTargetIdentifier):
        var_name = node.value

        range = search_scope(var_name, node, scope)

        if not range:
            return
        
        return lsp.Location(params.text_document.uri, range)
