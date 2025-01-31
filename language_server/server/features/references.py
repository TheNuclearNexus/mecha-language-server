from bolt import AstIdentifier, AstTargetIdentifier
from lsprotocol import types as lsp

from .. import MechaLanguageServer
from .helpers import (
    fetch_compilation_data,
    get_node_at_position,
    node_location_to_range,
    search_scope_for_binding,
)


def get_references(ls: MechaLanguageServer, params: lsp.ReferenceParams):
    compiled_doc = fetch_compilation_data(ls, params)

    if compiled_doc is None or compiled_doc.compiled_module is None:
        return

    ast = compiled_doc.compiled_module.ast
    scope = compiled_doc.compiled_module.lexical_scope

    node = get_node_at_position(ast, params.position)
    if isinstance(node, AstIdentifier) or isinstance(node, AstTargetIdentifier):
        var_name = node.value

        binding = search_scope_for_binding(var_name, node, scope)
        if not (result := search_scope_for_binding(var_name, node, scope)):
            return

        binding, _ = result

        locations = []
        for reference in binding.references:
            range = node_location_to_range(reference)
            locations.append(lsp.Location(params.text_document.uri, range))

        return locations
