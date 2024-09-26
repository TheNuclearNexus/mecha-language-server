from lsprotocol import types as lsp
from mecha import AstNode, AstResourceLocation
from mecha.contrib.nested_location import AstNestedLocation, NestedLocationResolver, NestedLocationTransformer
from mecha.contrib.relative_location import resolve_relative_location

from .helpers import fetch_compilation_data, get_node_at_position, node_location_to_range



from .. import MechaLanguageServer


def resolve_paths(root: AstNode, path: str = "current"):
    next_path = path
    for child in root:
        if isinstance(child, AstNestedLocation):
            child.__dict__["resolved_path"] = path + "/" + child.path     
            next_path = path + "/" + child.path
        elif isinstance(child, AstResourceLocation):
            next_path = child.path
        
        resolve_paths(child, next_path)

def get_hover(ls: MechaLanguageServer, params: lsp.HoverParams):
    compiled_doc = fetch_compilation_data(ls, params)
    
    if compiled_doc is None or compiled_doc.compiled_module is None:
        return
    
    compiled_module = compiled_doc.compiled_module

    resolver = NestedLocationResolver(compiled_doc.ctx)

    ast = compiled_module.ast
    
    resolve_paths(ast, path = "/".join(compiled_doc.resource_location.split(":")[1:]))

    node = get_node_at_position(ast, params.position)
    range = node_location_to_range(node)

    match node:
        case AstNestedLocation():
            path = node.__dict__.get("resolved_path")
            
            if path is None:
                return

            namespace, path = resolve_relative_location(path, compiled_doc.resource_location)
            return lsp.Hover(f"{namespace}:{path}", range)

        case AstResourceLocation():
            return lsp.Hover(f"{node.namespace}:{node.path}", range)