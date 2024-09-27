import logging
from bolt import AstIdentifier, AstTargetIdentifier, Binding, LexicalScope
from lsprotocol import types as lsp

from .validate import get_compilation_data

from .helpers import (
    fetch_compilation_data,
    get_node_at_position,
    node_location_to_range,
    node_start_to_range,
    search_scope_for_binding,
)

from .. import MechaLanguageServer




def get_definition(ls: MechaLanguageServer, params: lsp.DefinitionParams):
    compiled_doc = fetch_compilation_data(ls, params)

    if compiled_doc is None or compiled_doc.compiled_module is None:
        return

    ast = compiled_doc.compiled_module.ast
    scope = compiled_doc.compiled_module.lexical_scope

    node = get_node_at_position(ast, params.position)
    if isinstance(node, AstIdentifier) or isinstance(node, AstTargetIdentifier):
        var_name = node.value

        binding, scope = search_scope_for_binding(var_name, node, scope)

        if not binding:
            return
        
        range = node_location_to_range(binding.origin)
        
        return lsp.Location(params.text_document.uri, range)
