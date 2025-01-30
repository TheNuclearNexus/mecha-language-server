import json
from lsprotocol import types as lsp
from mecha import AstNode, AstResourceLocation
from mecha.contrib.nested_location import (
    AstNestedLocation,
    NestedLocationResolver,
    NestedLocationTransformer,
)
from mecha.contrib.relative_location import resolve_relative_location

from .helpers import (
    fetch_compilation_data,
    get_node_at_position,
    node_location_to_range,
)


from .. import MechaLanguageServer

DEBUG_AST = False

def get_hover(ls: MechaLanguageServer, params: lsp.HoverParams):
    compiled_doc = fetch_compilation_data(ls, params)

    if compiled_doc is None or compiled_doc.ast is None:
        return

    ast = compiled_doc.ast

    node = get_node_at_position(ast, params.position)
    range = node_location_to_range(node)

    match node:
        case AstResourceLocation():
            represents = node.__dict__.get("represents")
            namespace = node.namespace or 'minecraft'

            if isinstance(node, AstNestedLocation):
                path = node.__dict__.get("resolved_path")

                if path is not None:
                    namespace, path = resolve_relative_location(
                        path, compiled_doc.resource_location.split("/")[0], include_root_file=False
                    )
                else:
                    path = node.path
                
            else:
                path = node.path

            return lsp.Hover(
                lsp.MarkupContent(
                    lsp.MarkupKind.Markdown, 
                    f"**type**: `{represents}`\n```yaml\n{namespace or 'minecraft'}:{path}\n```"
                ), 
                range
            )
        case _:
            if DEBUG_AST:
                return lsp.Hover(
                    lsp.MarkupContent(
                        lsp.MarkupKind.Markdown,
                        f"Repr: `{node.__repr__()}`\n\nDict: ```{node.__dict__.__repr__()}```"
                    ),
                    range
                )