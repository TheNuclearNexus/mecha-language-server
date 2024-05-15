import logging
import traceback
from typing import Any
from beet import Function, TextFileBase
from lsprotocol import types as lsp
from mecha import AstRoot, CompilationUnit
from mecha.ast import AstError
from tokenstream import InvalidSyntax, TokenStream, UnexpectedToken

from .. import MechaLanguageServer


def validate(ls: MechaLanguageServer, params: lsp.DidOpenTextDocumentParams):
    text_doc = ls.workspace.get_document(params.text_document.uri)

    diagnostics = validate_function(ls, text_doc.source)
    diagnostics = [
        tokenstream_error_to_lsp_diag(d, type(ls).__name__, text_doc.filename)
        for d in diagnostics
    ]
    logging.debug(f"Sending diagnostics: {diagnostics}")

    ls.publish_diagnostics(
        params.text_document.uri,
        diagnostics,
    )


def tokenstream_error_to_lsp_diag(
    exec: InvalidSyntax, source: str, filename: str
) -> lsp.Diagnostic:
    range = [exec.location, exec.end_location]
    if isinstance(exec, UnexpectedToken):
        range = [exec.token.location, exec.token.end_location]
    
    # trace = '\n'.join(traceback.format_tb(exec.__traceback__))
    # logging.debug(trace)

    return lsp.Diagnostic(
        range=lsp.Range(
            start=lsp.Position(
                line=range[0].lineno - 1, character=range[0].colno - 1
            ),
            end=lsp.Position(
                line=range[1].lineno - 1, character=range[1].colno - 1
            ),
        ),
        message=f"{exec.format(filename)}\n{type(exec).__name__}", #\n{exec.format(filename)}\n\n{trace}
        source=source,
    )


def validate_function(ls: MechaLanguageServer, source: str) -> list[InvalidSyntax]:
    diagnostics = []
    try:
        ast = parse_function(ls, source)
    except InvalidSyntax as exec:
        ls.send_notification("Failed to parse")
        logging.error(f"Failed to parse: {exec}")
        diagnostics.append(exec)
    else:
        for node in ast.walk():
            if isinstance(node, AstError):
                diagnostics.append(node.error)

    return diagnostics


def parse_function(
    ls: MechaLanguageServer, function: TextFileBase[Any] | list[str] | str
) -> AstRoot:
    if not isinstance(function, TextFileBase):
        function = Function(function)

    stream = TokenStream(
        source=function.text,
        preprocessor=ls.mecha.preprocessor,
    )

    mecha = ls.mecha
    mecha.database.current = function
    mecha.database[function] = CompilationUnit(resource_location="lsp:current")

    ast = mecha.parse_stream(ls.mecha.spec.multiline, None, AstRoot.parser, stream)

    return ast
