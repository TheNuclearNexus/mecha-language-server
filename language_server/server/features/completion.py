import logging
from lsprotocol import types as lsp
from mecha import AstOption, AstSwizzle, BasicLiteralParser, Mecha
from bolt import UndefinedIdentifier
from tokenstream import UnexpectedEOF, UnexpectedToken
from pygls.workspace import TextDocument

from ...server import MechaLanguageServer
from .validate import get_compilation_data, validate_function
from mecha.ast import AstError

TOKEN_HINTS: dict[str, list[str]] = {
    "player_name": ["@s", "@e", "@p", "@a", "@r"],
    "coordinate": ["~ ~ ~", "^ ^ ^"]
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
    mecha = ls.get_mecha(text_doc)

    items = get_completions(ls, mecha, params.position, text_doc)

    return lsp.CompletionList(False, items)

def get_completions(ls: MechaLanguageServer, mecha: Mecha, pos: lsp.Position, text_doc: TextDocument) -> list[lsp.CompletionItem]:
    _, diagnostics = get_compilation_data(ls, mecha, text_doc)

    items = []
    for diagnostic in diagnostics:
        start = diagnostic.location
        end = diagnostic.end_location

        if start.colno <= pos.character + 1 and end.colno >= pos.character:
            if isinstance(diagnostic, UnexpectedToken) or isinstance(
                diagnostic, UnexpectedEOF
            ):
                for pattern in diagnostic.expected_patterns:
                    [token_type, value] = (
                        pattern if isinstance(pattern, tuple) else [pattern, None]
                    )
                    items += get_token_options(mecha, token_type, value)

                logging.debug(f"\n\n{diagnostic.expected_patterns}\n\n")
                break

            if isinstance(diagnostic, UndefinedIdentifier):
                for name in diagnostic.lexical_scope.variables:
                    items.append(lsp.CompletionItem(name))
                    logging.debug(diagnostic.lexical_scope.variables[name])
                break
    return items
