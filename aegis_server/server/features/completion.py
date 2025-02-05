import builtins
import inspect
from functools import reduce
from typing import Any

from bolt import AstAttribute, Runtime, UndefinedIdentifier, Variable
from lsprotocol import types as lsp
from mecha import (
    AstNode,
    Mecha,
)
from pygls.workspace import TextDocument
from tokenstream import UnexpectedEOF, UnexpectedToken

from aegis.ast.features import AegisFeatureProviders
from aegis.ast.features.provider import CompletionParams
from aegis.reflection import (
    UNKNOWN_TYPE,
    FunctionInfo,
    TypeInfo,
    get_annotation_description,
    get_function_description,
    get_type_info,
)
from aegis_server.server.features.helpers import get_node_at_position

from ...server import GAME_REGISTRIES, AegisServer
from ..indexing import get_type_annotation
from ..shadows.compile_document import CompilationError
from ..shadows.context import LanguageServerContext
from .validate import get_compilation_data


def completion(ls: AegisServer, params: lsp.CompletionParams):
    text_doc = ls.workspace.get_document(params.text_document.uri)

    with ls.context(text_doc) as ctx:
        if ctx is None:
            items = []
        else:
            items = get_completions(ctx, params.position, text_doc)

        return lsp.CompletionList(False, items or [])


def get_completions(
    ctx: LanguageServerContext,
    pos: lsp.Position,
    text_doc: TextDocument,
) -> list[lsp.CompletionItem] | None:
    mecha = ctx.inject(Mecha)

    if not (compiled_doc := get_compilation_data(ctx, text_doc)):
        return []

    ast = compiled_doc.ast
    diagnostics = compiled_doc.diagnostics

    if len(diagnostics) > 0:
        return get_diag_completions(pos, mecha, ctx.inject(Runtime), diagnostics)
    elif ast is not None:
        node = get_node_at_position(ast, pos)

        provider = compiled_doc.ctx.inject(AegisFeatureProviders).retrieve(node)
        return provider.completion(CompletionParams(compiled_doc.ctx, node))


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
