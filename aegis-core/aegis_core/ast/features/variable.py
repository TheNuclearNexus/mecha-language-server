import lsprotocol.types as lsp
from bolt import AstAttribute, AstIdentifier, AstImportedItem, AstTargetAttribute, AstTargetIdentifier

from ...reflection import get_annotation_description
from ..metadata import VariableMetadata, retrieve_metadata
from . import BaseFeatureProvider

__all__ = ["VariableFeatureProvider"]


class VariableFeatureProvider(
    BaseFeatureProvider[
        AstIdentifier | AstAttribute | AstTargetAttribute | AstTargetIdentifier | AstImportedItem
    ]
):
    @classmethod
    def hover(cls, params) -> lsp.Hover | None:
        node = params.node
        text_range = params.text_range

        metadata = retrieve_metadata(node, VariableMetadata)
        name = (
            node.value
            if not isinstance(node, (AstAttribute, AstTargetAttribute, AstImportedItem))
            else node.name
        )

        if metadata and metadata.type_annotation:

            type_annotation = metadata.type_annotation

            description = get_annotation_description(name, type_annotation)

            return lsp.Hover(
                lsp.MarkupContent(lsp.MarkupKind.Markdown, description), text_range
            )

        return lsp.Hover(
            lsp.MarkupContent(
                lsp.MarkupKind.Markdown,
                f"```python\n(variable) {name}\n```",
            ),
            text_range,
        )
