import builtins
import inspect
import logging
from pathlib import Path
import types
from functools import reduce
from typing import Any, cast

from beet import File, NamespaceFile
from bolt import AstAttribute, AstIdentifier, Runtime, UndefinedIdentifier, Variable
from lsprotocol import types as lsp
from mecha import (
    AstCommand,
    AstItemSlot,
    AstNode,
    AstOption,
    AstResourceLocation,
    BasicLiteralParser,
    Mecha,
)
from pygls.workspace import TextDocument
from tokenstream import InvalidSyntax, UnexpectedEOF, UnexpectedToken

from language_server.server.features.helpers import (
    get_annotation_description,
    get_class_description,
    get_function_description,
    get_node_at_position,
    get_variable_description,
    node_location_to_range,
)

from ...server import GAME_REGISTRIES, MechaLanguageServer
from ..indexing import ProjectIndex, get_type_annotation
from ..shadows.context import LanguageServerContext
from ..shadows.compile_document import CompilationError
from ..utils.reflection import (
    UNKNOWN_TYPE,
    FunctionInfo,
    TypeInfo,
    format_function_hints,
    get_name_of_type,
    get_type_info,
)
from .validate import get_compilation_data

TOKEN_HINTS: dict[str, list[str]] = {
    "player_name": ["@s", "@e", "@p", "@a", "@r"],
    "coordinate": ["~ ~ ~", "^ ^ ^"],
    "item_slot": [
        "contents",
        "container.",
        "hotbar.",
        "inventory.",
        "enderchest.",
        "villager.",
        "horse.",
        "weapon",
        "weapon.mainhand",
        "weapon.offhand",
        "armor.head",
        "armor.chest",
        "armor.legs",
        "armor.feet",
        "armor.body",
        "horse.saddle",
        "horse.chest",
        "player.cursor",
        "player.crafting.\1",
    ],
}


def get_token_options(mecha: Mecha, token_type: str, value: str | None):
    # Use manually defined hints first
    if token_type in TOKEN_HINTS:
        return [lsp.CompletionItem(k) for k in TOKEN_HINTS[token_type]]

    if value == None:
        if token_type not in mecha.spec.parsers:
            return []

        parser = mecha.spec.parsers[token_type]

        # logging.debug(f"Pulling value from: {parser}")
        if isinstance(parser, BasicLiteralParser):
            node_type = parser.type
            # logging.debug(f"Node type: {node_type}")

            if issubclass(node_type, AstOption):
                # logging.debug(f"Options: {node_type.options}")
                return [
                    lsp.CompletionItem(o, kind=lsp.CompletionItemKind.Keyword)
                    for o in node_type.options
                ]
    else:
        return [lsp.CompletionItem(value)]

    return []


def completion(ls: MechaLanguageServer, params: lsp.CompletionParams):
    text_doc = ls.workspace.get_document(params.text_document.uri)

    with ls.context(text_doc) as ctx:
        if ctx is None:
            items = []
        else:
            items = get_completions(ctx, params.position, text_doc)

        return lsp.CompletionList(False, items)


def get_path(path: str) -> tuple[str | None, Path]:
    segments = path.split(":")
    if len(segments) == 1:
        return (None, Path(segments[0]))
    else:
        return (segments[0], Path(segments[1]))


def get_completions(
    ctx: LanguageServerContext,
    pos: lsp.Position,
    text_doc: TextDocument,
) -> list[lsp.CompletionItem]:
    mecha = ctx.inject(Mecha)

    if not (compiled_doc := get_compilation_data(ctx, text_doc)):
        return []

    ast = compiled_doc.ast
    diagnostics = compiled_doc.diagnostics

    items = []
    if len(diagnostics) > 0:
        items = get_diag_completions(pos, mecha, ctx.inject(Runtime), diagnostics)
    elif ast is not None:
        current_node = get_node_at_position(ast, pos)

        if isinstance(current_node, AstResourceLocation):
            represents = current_node.__dict__.get("represents")
            # logging.debug(GAME_REGISTRIES)
            if represents and issubclass(represents, File):
                file_type = cast(type[NamespaceFile], represents)

                path = current_node.get_canonical_value()

                if current_node.is_tag:
                    path = path[1:]

                project_index = ProjectIndex.get(ctx)

                resolved = get_path(path)

                unresolved = get_path(current_node.__dict__["unresolved_path"])

                if unresolved[1].name == "~":
                    resolved_parent = resolved[1]
                    unresolved_parent = unresolved[1]
                else:
                    resolved_parent = resolved[1].parent
                    unresolved_parent = unresolved[1].parent

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
                    if current_node.is_tag:
                        insert_text = "#" + insert_text

                    items.append(
                        lsp.CompletionItem(
                            label=insert_text,
                            documentation=file,
                            text_edit=lsp.InsertReplaceEdit(
                                insert_text,
                                node_location_to_range(current_node),
                                node_location_to_range(current_node),
                            ),
                        )
                    )

            elif isinstance(represents, str):
                add_registry_items(items, represents)
                add_registry_items(
                    items, "tag/" + represents, "#", lsp.CompletionItemKind.Constant
                )

        if isinstance(current_node, AstItemSlot):
            items.extend(
                [
                    lsp.CompletionItem(k, kind=lsp.CompletionItemKind.Value)
                    for k in TOKEN_HINTS["item_slot"]
                ]
            )

        # logging.debug(f"\n\n{current_node}\n\n")
        if isinstance(current_node, AstIdentifier) or isinstance(
            current_node, AstAttribute
        ):
            get_bolt_completions(current_node, items)

    return items


def add_registry_items(
    items: list[lsp.CompletionItem],
    represents: str,
    prefix: str = "",
    kind: lsp.CompletionItemKind = lsp.CompletionItemKind.Value,
):
    if represents in GAME_REGISTRIES:
        registry_items = GAME_REGISTRIES[represents]
        items.extend(
            [
                lsp.CompletionItem(prefix + "minecraft:" + k, kind=kind, sort_text=k)
                for k in registry_items
            ]
        )


def get_bolt_completions(
    node: AstNode,
    items: list[lsp.CompletionItem],
):
    if isinstance(node, AstAttribute):
        node = node.value

    type_annotation = get_type_annotation(node)

    if type_annotation is UNKNOWN_TYPE:
        return

    type_info = (
        get_type_info(type_annotation)
        if not isinstance(type_annotation, TypeInfo)
        else type_annotation
    )

    for name, type in type_info.fields.items():
        add_variable_completion(items, name, type)

    for name, function_info in type_info.functions.items():
        items.append(
            lsp.CompletionItem(
                name,
                kind=lsp.CompletionItemKind.Function,
                documentation=lsp.MarkupContent(
                    kind=lsp.MarkupKind.Markdown,
                    value=get_function_description(name, function_info),
                ),
            )
        )


def get_diag_completions(
    pos: lsp.Position,
    mecha: Mecha,
    runtime: Runtime,
    diagnostics: list[CompilationError],
):
    items = []
    for diagnostic in diagnostics:
        start = diagnostic.location
        end = diagnostic.end_location

        if not (start.colno <= pos.character + 1 and end.colno >= pos.character):
            continue

        if isinstance(diagnostic, UnexpectedToken) or isinstance(
            diagnostic, UnexpectedEOF
        ):
            for pattern in diagnostic.expected_patterns:
                [token_type, value] = (
                    pattern if isinstance(pattern, tuple) else [pattern, None]
                )
                items += get_token_options(mecha, token_type, value)
            break

        if isinstance(diagnostic, UndefinedIdentifier):
            for name, variable in diagnostic.lexical_scope.variables.items():
                add_variable_definition(items, name, variable)

            for name, value in runtime.globals.items():
                add_raw_definition(items, name, value)

            for name in runtime.builtins:
                add_raw_definition(items, name, getattr(builtins, name))

            break
    return items


def add_variable_definition(
    items: list[lsp.CompletionItem], name: str, variable: Variable
):
    possible_types = set()

    for binding in variable.bindings:
        origin = binding.origin
        if annotation := get_type_annotation(origin):
            possible_types.add(annotation)

    if len(possible_types) > 0:
        _type = reduce(lambda a, b: a | b, possible_types)
        add_variable_completion(items, name, _type)


def add_raw_definition(items: list[lsp.CompletionItem], name: str, value: Any):
    if inspect.isclass(value) or isinstance(value, TypeInfo):
        add_class_completion(items, name, value)
    elif (
        inspect.isfunction(value)
        or inspect.isbuiltin(value)
        or isinstance(value, FunctionInfo)
    ):
        add_function_completion(items, name, value)
    else:
        add_variable_completion(items, name, type(value))


def add_class_completion(
    items: list[lsp.CompletionItem], name: str, type_annotation: Any
):
    description = get_annotation_description(name, type_annotation)
    documentation = lsp.MarkupContent(lsp.MarkupKind.Markdown, description)

    items.append(
        lsp.CompletionItem(
            name, documentation=documentation, kind=lsp.CompletionItemKind.Class
        )
    )


def add_function_completion(items: list[lsp.CompletionItem], name: str, function: Any):
    description = get_annotation_description(name, function)
    documentation = lsp.MarkupContent(lsp.MarkupKind.Markdown, description)

    items.append(
        lsp.CompletionItem(
            name, documentation=documentation, kind=lsp.CompletionItemKind.Function
        )
    )


def add_variable_completion(
    items: list[lsp.CompletionItem], name: str, type_annotation: Any
):
    kind = (
        lsp.CompletionItemKind.Property
        if not name.isupper()
        else lsp.CompletionItemKind.Constant
    )

    description = get_annotation_description(name, type_annotation)
    documentation = lsp.MarkupContent(lsp.MarkupKind.Markdown, description)

    items.append(lsp.CompletionItem(name, documentation=documentation, kind=kind))
