import logging
from lsprotocol import types as lsp
from mecha import AstOption, AstSwizzle, BasicLiteralParser, Mecha
from tokenstream import UnexpectedEOF, UnexpectedToken

from ...server import MechaLanguageServer
from .validate import validate_function
from mecha.ast import AstError

TOKEN_HINTS: dict[str, list[str]] = {
    "player_name": ["@s", "@e", "@p", "@a", "@r"],
    "coordinate": ["~ ~ ~", "^ ^ ^"]
}


def get_items(mecha: Mecha, token_type: str, value: str | None):

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

    diagnostics = validate_function(ls, text_doc.source)

    pos = params.position
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
                    items += get_items(ls.mecha, token_type, value)

                logging.debug(f"\n\n{diagnostic.expected_patterns}\n\n")
                break

    return lsp.CompletionList(False, items)
