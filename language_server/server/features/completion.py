import logging

from bolt import AstAttribute, AstIdentifier, UndefinedIdentifier, Variable
from lsprotocol import types as lsp
from mecha import (
    AstItemSlot,
    AstNode,
    AstOption,
    AstResourceLocation,
    BasicLiteralParser,
    Mecha,
)
from pygls.workspace import TextDocument
from tokenstream import InvalidSyntax, UnexpectedEOF, UnexpectedToken

from language_server.server.features.helpers import get_node_at_position
from language_server.server.shadows import CompiledDocument, LanguageServerContext

from ...server import GAME_REGISTRIES, MechaLanguageServer
from ..indexing import get_type_annotation
from ..utils.reflection import (
    UNKNOWN_TYPE,
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
    ctx = ls.get_context(text_doc)

    if ctx is None:
        items = []
    else:
        items = get_completions(ls, ctx, params.position, text_doc)

    return lsp.CompletionList(False, items)


def get_completions(
    ls: MechaLanguageServer,
    ctx: LanguageServerContext,
    pos: lsp.Position,
    text_doc: TextDocument,
) -> list[lsp.CompletionItem]:
    mecha = ctx.inject(Mecha)
    compiled_doc = get_compilation_data(ls, ctx, text_doc)

    ast = compiled_doc.ast
    diagnostics = compiled_doc.diagnostics

    items = []
    if len(diagnostics) > 0:
        items = get_diag_completions(pos, mecha, diagnostics)
    elif ast is not None:
        current_node = get_node_at_position(ast, pos)

        if isinstance(current_node, AstResourceLocation):
            represents = current_node.__dict__.get("represents")
            # logging.debug(GAME_REGISTRIES)
            if represents is not None:
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
    logging.debug(type_annotation)

    if type_annotation is UNKNOWN_TYPE:
        return

    type_info = get_type_info(type_annotation)
    logging.debug(type_info)

    for name, type in type_info.fields.items():
        kind = (
            lsp.CompletionItemKind.Property
            if not name.isupper()
            else lsp.CompletionItemKind.Constant
        )

        items.append(
            lsp.CompletionItem(
                name,
                kind=kind,
                documentation=lsp.MarkupContent(
                    kind=lsp.MarkupKind.Markdown,
                    value=f"```py\n{name}: {get_name_of_type(type)}\n```\n{type.__doc__ or ''}",
                ),
            )
        )

    for name, function_info in type_info.functions.items():
        items.append(
            lsp.CompletionItem(
                name,
                kind=lsp.CompletionItemKind.Function,
                documentation=lsp.MarkupContent(
                    kind=lsp.MarkupKind.Markdown,
                    value=f"```py\n(function) {format_function_hints(name, function_info)}\n```\n{function_info.doc or ''}",
                ),
            )
        )


def get_diag_completions(
    pos: lsp.Position, mecha: Mecha, diagnostics: list[InvalidSyntax]
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
                add_variable(items, name, variable)

            break
    return items


def add_variable(items: list[lsp.CompletionItem], name: str, variable: Variable):

    possible_types = set()
    documentation = None

    for binding in variable.bindings:
        origin = binding.origin
        if type_annotations := origin.__dict__.get("type_annotations"):
            for t in type_annotations:
                match t:
                    case AstIdentifier() as identifer:
                        possible_types.add(identifer.value)
                    case type() as _type:
                        possible_types.add(_type.__name__)
                    case _:
                        possible_types.add(str(type_annotations))

    if len(possible_types) > 0:
        description = f"```python\n{name}: {' | '.join(possible_types)}\n```"
        documentation = lsp.MarkupContent(lsp.MarkupKind.Markdown, description)

    items.append(
        lsp.CompletionItem(
            name, documentation=documentation, kind=lsp.CompletionItemKind.Variable
        )
    )
