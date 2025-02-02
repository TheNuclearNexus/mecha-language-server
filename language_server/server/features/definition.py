import logging
from pathlib import Path
from typing import cast

from beet import NamespaceFile
from bolt import AstIdentifier, AstTargetIdentifier, Binding, LexicalScope
from lsprotocol import types as lsp
from mecha import AstResourceLocation

from ..indexing import ProjectIndex

from .. import MechaLanguageServer
from .helpers import (
    fetch_compilation_data,
    get_node_at_position,
    get_representation_file,
    node_location_to_range,
    node_start_to_range,
    search_scope_for_binding,
)
from .validate import get_compilation_data


def get_definition(ls: MechaLanguageServer, params: lsp.DefinitionParams):
    compiled_doc = fetch_compilation_data(ls, params)

    if compiled_doc is None or compiled_doc.ast is None:
        return

    project_index = ProjectIndex.get(compiled_doc.ctx)
    node = get_node_at_position(compiled_doc.ast, params.position)

    if isinstance(node, AstResourceLocation):
        if not (represents := get_representation_file(project_index, node)):
            return 
        
        path = node.get_canonical_value()
        definitions = project_index[represents].get_definitions(path)
        
        return [
            lsp.LocationLink(
                target_uri=Path(path).as_uri(),
                target_range=node_location_to_range(location),
                target_selection_range=node_location_to_range(location),
                origin_selection_range=node_location_to_range(node)
            ) for path, *location in definitions
        ]

    if compiled_doc.compiled_module is None:
        return

    scope = compiled_doc.compiled_module.lexical_scope

    if isinstance(node, AstIdentifier):
        var_name = node.value

        result = search_scope_for_binding(var_name, node, scope)

        if not result:
            return

        binding, scope = result

        range = node_location_to_range(binding.origin)

        return lsp.Location(params.text_document.uri, range)
        