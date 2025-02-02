from pathlib import Path
from bolt import AstIdentifier, AstTargetIdentifier
from lsprotocol import types as lsp
from mecha import AstResourceLocation

from ..indexing import ProjectIndex

from .. import MechaLanguageServer
from .helpers import (
    fetch_compilation_data,
    get_node_at_position,
    get_representation_file,
    node_location_to_range,
    search_scope_for_binding,
)


def get_references(ls: MechaLanguageServer, params: lsp.ReferenceParams):
    compiled_doc = fetch_compilation_data(ls, params)

    if compiled_doc is None or compiled_doc.ast is None:
        return

    project_index = ProjectIndex.get(compiled_doc.ctx)
    node = get_node_at_position(compiled_doc.ast, params.position)


    if isinstance(node, AstResourceLocation):
        if not (represents := get_representation_file(project_index, node)):
            return 
        
        path = node.get_canonical_value()
        references = project_index[represents].get_references(path)
        
        return [
            lsp.Location(
                Path(path).as_uri(),
                node_location_to_range(location)
            ) for path, *location in references
        ]
    
    if  compiled_doc.compiled_module is None:
        return

    scope = compiled_doc.compiled_module.lexical_scope

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
