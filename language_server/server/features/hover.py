from beet import File
from bolt import (
    AstAttribute,
    AstCall,
    AstIdentifier,
    AstImportedItem,
    AstTargetIdentifier,
)
from lsprotocol import types as lsp
from mecha import AstResourceLocation

from ..utils.reflection import FunctionInfo, TypeInfo, get_type_info

from ..indexing import get_type_annotation

from .. import MechaLanguageServer
from .helpers import (
    fetch_compilation_data,
    get_annotation_description,
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

        case (
            AstIdentifier() | AstAttribute() | AstTargetIdentifier() | AstImportedItem()
        ):
            type_annotation = get_type_annotation(node)

            var_name = (
                node.value
                if not isinstance(node, (AstAttribute, AstImportedItem))
                else node.name
            )

            if not type_annotation:
                return lsp.Hover(
                    lsp.MarkupContent(
                        lsp.MarkupKind.Markdown,
                        f"```python\n(variable) {var_name}\n```",
                    )
                )

            description = get_annotation_description(var_name, type_annotation)

            return lsp.Hover(lsp.MarkupContent(lsp.MarkupKind.Markdown, description))