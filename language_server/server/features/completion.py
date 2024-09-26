import logging
from beet import Context
from lsprotocol import types as lsp
from mecha import AstOption, AstSwizzle, BasicLiteralParser, Mecha, Reducer
from bolt import AstAttribute, AstIdentifier, UndefinedIdentifier, Variable
from tokenstream import InvalidSyntax, SourceLocation, UnexpectedEOF, UnexpectedToken
from pygls.workspace import TextDocument

from language_server.server.features.helpers import get_node_at_position
from language_server.server.indexing import AstTypedTarget, AstTypedTargetIdentifier

from ...server import MechaLanguageServer
from .validate import get_compilation_data
from mecha.ast import AstError

TOKEN_HINTS: dict[str, list[str]] = {
    "player_name": ["@s", "@e", "@p", "@a", "@r"],
    "coordinate": ["~ ~ ~", "^ ^ ^"],
}


def get_token_options(mecha: Mecha, token_type: str, value: str | None):
    # Use manually defined hints first
    if token_type in TOKEN_HINTS:
        return [lsp.CompletionItem(k) for k in TOKEN_HINTS[token_type]]

    if value == None:
        if token_type not in mecha.spec.parsers:
            return []

        parser = mecha.spec.parsers[token_type]

        logging.debug(f"Pulling value from: {parser}")
        if isinstance(parser, BasicLiteralParser):
            node_type = parser.type
            logging.debug(f"Node type: {node_type}")

            if issubclass(node_type, AstOption):
                logging.debug(f"Options: {node_type.options}")
                return [lsp.CompletionItem(o) for o in node_type.options]
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
    ls: MechaLanguageServer, ctx: Context, pos: lsp.Position, text_doc: TextDocument
) -> list[lsp.CompletionItem]:
    mecha = ctx.inject(Mecha)
    compiled_doc = get_compilation_data(ls, ctx, text_doc)

    ast = compiled_doc.ast
    diagnostics = compiled_doc.diagnostics

    logging.debug(f"\n\n{compiled_doc.compiled_module}\n\n")

    items = []
    if len(diagnostics) > 0:
        items = get_diag_completions(pos, mecha, diagnostics)
    elif ast is not None:
        current_token = get_node_at_position(
            ast, pos
        )

        if isinstance(current_token, AstAttribute) and compiled_doc.compiled_module is not None:
            module = compiled_doc.compiled_module
            value = current_token.value
            if isinstance(value, AstIdentifier):
                var_name = value.value
                defined_variables = module.lexical_scope.variables
                variable = defined_variables[var_name]

                for binding in variable.bindings:
                    if value in binding.references and (type_annotations := binding.origin.__dict__.get("type_annotations")):
                        for type_annotation in type_annotations:
                            if not isinstance(type_annotation, type):
                                continue
                            
                            for field in dir(type_annotation): 
                                items.append(lsp.CompletionItem(field))


    return items


def get_diag_completions(pos: lsp.Position, mecha: Mecha, diagnostics: list[InvalidSyntax]):
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
            logging.debug("undefined identifier")
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

    items.append(lsp.CompletionItem(name, documentation=documentation))
