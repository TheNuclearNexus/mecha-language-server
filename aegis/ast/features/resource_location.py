__all__ = ["ResourceLocationFeatureProvider"]

from pathlib import Path
from typing import cast
from beet import File, NamespaceFile
from mecha import AstResourceLocation
import lsprotocol.types as lsp

from ...ast.helpers import node_location_to_range

from ...ast.metadata import ResourceLocationMetadata, retrieve_metadata
from ...indexing.project_index import AegisProjectIndex
from .provider import BaseFeatureProvider


def get_path(path: str) -> tuple[str | None, Path]:
    segments = path.split(":")
    if len(segments) == 1:
        return (None, Path(segments[0]))
    else:
        return (segments[0], Path(segments[1]))

class ResourceLocationFeatureProvider(BaseFeatureProvider[AstResourceLocation]):
    @classmethod
    def hover(cls, params) -> lsp.Hover | None:
        node = params.node
        text_range = params.text_range

        metadata = retrieve_metadata(node, ResourceLocationMetadata)

        if metadata is None or metadata.represents is None:
            path_type = None
        elif isinstance(metadata.represents, str):
            path_type = metadata.represents
        elif issubclass(metadata.represents, File):
            path_type = metadata.represents.snake_name

        type_line = f"**{path_type}**\n" if path_type else ""

        return lsp.Hover(
            lsp.MarkupContent(
                lsp.MarkupKind.Markdown,
                f"{type_line}```yaml\n{node.get_canonical_value()}\n```",
            ),
            text_range,
        )

    @classmethod
    def definition(cls, params):
        project_index = params.ctx.inject(AegisProjectIndex)
        node = params.node

        metadata = retrieve_metadata(node, ResourceLocationMetadata)

        if not metadata or metadata.represents is not type[NamespaceFile]:
            return

        path = node.get_canonical_value()
        definitions = project_index[metadata.represents].get_definitions(path)

        return [
            lsp.LocationLink(
                target_uri=Path(path).as_uri(),
                target_range=node_location_to_range(location),
                target_selection_range=node_location_to_range(location),
                origin_selection_range=node_location_to_range(node),
            )
            for path, *location in definitions
        ]

    @classmethod
    def references(cls, params) -> list[lsp.Location] | None:
        project_index = params.ctx.inject(AegisProjectIndex)
        node = params.node

        metadata = retrieve_metadata(node, ResourceLocationMetadata)

        if not metadata or metadata.represents is not type[NamespaceFile]:
            return

        path = node.get_canonical_value()
        references = project_index[metadata.represents].get_references(path)

        return [
            lsp.Location(Path(path).as_uri(), node_location_to_range(location))
            for path, *location in references
        ]

    @classmethod
    def completion(cls, params):
        node = params.node
        project_index = params.ctx.inject(AegisProjectIndex)

        metadata = retrieve_metadata(node, ResourceLocationMetadata)

        if not metadata or metadata.represents is not type[NamespaceFile]:
            return

        represents = metadata.represents

        if represents is type[NamespaceFile]:
            file_type = cast(type[NamespaceFile], represents)

            path = node.get_canonical_value()

            if node.is_tag:
                path = path[1:]

            resolved = get_path(path)

            unresolved = get_path(metadata.unresolved_path or path)

            if unresolved[1].name == "~":
                resolved_parent = resolved[1]
                unresolved_parent = unresolved[1]
            else:
                resolved_parent = resolved[1].parent
                unresolved_parent = unresolved[1].parent

            items = []

            for file in project_index[file_type]:
                file_path = get_path(file)

                if not (
                    file_path[0] == resolved[0]
                    and file_path[1].is_relative_to(resolved_parent)
                ):
                    continue

                relative = file_path[1].relative_to(resolved_parent)

                if unresolved[0] is None and unresolved[1].name == "":
                    new_path = "./" + str(relative)
                else:
                    new_path = str(unresolved_parent / relative)

                insert_text = (
                    f"{unresolved[0] + ':' if unresolved[0] else ''}{new_path}"
                )
                if node.is_tag:
                    insert_text = "#" + insert_text

                items.append(
                    lsp.CompletionItem(
                        label=insert_text,
                        documentation=file,
                        text_edit=lsp.InsertReplaceEdit(
                            insert_text,
                            node_location_to_range(node),
                            node_location_to_range(node),
                        ),
                    )
                )

                return items

        elif isinstance(represents, str):
            items = []

            add_registry_items(items, represents)
            add_registry_items(
                items, "tag/" + represents, "#", lsp.CompletionItemKind.Constant
            )

            return items
