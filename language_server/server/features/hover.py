import json

from beet import File
from lsprotocol import types as lsp
from mecha import AstNode, AstResourceLocation
from mecha.contrib.nested_location import (
    AstNestedLocation,
    NestedLocationResolver,
    NestedLocationTransformer,
)
from mecha.contrib.relative_location import resolve_relative_location

from .. import MechaLanguageServer
from .helpers import (
    fetch_compilation_data,
    get_node_at_position,
    node_location_to_range,
)

DEBUG_AST = False


def get_hover(ls: MechaLanguageServer, params: lsp.HoverParams):
    compiled_doc = fetch_compilation_data(ls, params)

    if compiled_doc is None or compiled_doc.ast is None:
        return

    ast = compiled_doc.ast

    node = get_node_at_position(ast, params.position)
    range = node_location_to_range(node)
      
    if DEBUG_AST:
        return lsp.Hover(
            lsp.MarkupContent(
                lsp.MarkupKind.Markdown,
                f"Repr: `{node.__repr__()}`\n\nDict: ```{node.__dict__.__repr__()}```",
            ),
            range,
        )
    
    match node:
        case AstResourceLocation():
            represents = node.__dict__.get("represents")

            if represents is None:
                path_type = None
            elif isinstance(represents, str):
                path_type = represents
            elif issubclass(represents, File):
                path_type = represents.snake_name

            type_line = f"**{path_type}**\n" if path_type else ""

            return lsp.Hover(
                lsp.MarkupContent(
                    lsp.MarkupKind.Markdown,
                    f"{type_line}```yaml\n{node.get_canonical_value()}\n```",
                ),
                range,
            )
  
