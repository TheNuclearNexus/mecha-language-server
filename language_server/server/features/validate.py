import logging
import traceback
from typing import Any
from beet import Function, TextFileBase
from lsprotocol import types as lsp
from mecha import AstRoot, CompilationUnit, Mecha
from mecha.ast import AstError
from tokenstream import InvalidSyntax, TokenStream, UnexpectedToken
from pygls.workspace import TextDocument

from .. import COMPILATION_RESULTS, MechaLanguageServer

def validate(ls: MechaLanguageServer, params: lsp.DidOpenTextDocumentParams):
    text_doc = ls.workspace.get_document(params.text_document.uri)
    mecha = ls.get_mecha(text_doc)

    diagnostics = validate_function(ls, mecha, text_doc)
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
    
    trace = '\n'.join(traceback.format_tb(exec.__traceback__))
    logging.debug(trace)

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



def get_compilation_data(ls: MechaLanguageServer, mecha: Mecha, text_doc: TextDocument):
    if text_doc.uri in COMPILATION_RESULTS:
        return COMPILATION_RESULTS[text_doc.uri]
    
    validate_function(ls, mecha, text_doc)
    return COMPILATION_RESULTS[text_doc.uri]
    


def validate_function(ls: MechaLanguageServer, mecha: Mecha, text_doc: TextDocument) -> list[InvalidSyntax]:
    diagnostics = []
    ast = None
    logging.debug(f"Parsing function:\n{text_doc.source}")
    try:
        ast = parse_function(mecha, text_doc.source)
    except InvalidSyntax as exec:
        ast = None
        ls.send_notification("Failed to parse")
        logging.error(f"Failed to parse: {exec}")
        diagnostics.append(exec)

    except KeyError as exec:
        tb = '\n'.join(traceback.format_tb(exec.__traceback__))
        logging.error(f"{tb}")
    except Exception as exec:
        logging.error(F"{type(exec)}: {exec}")

    else:
        for node in ast.walk():
            if isinstance(node, AstError):
                diagnostics.append(node.error)

    COMPILATION_RESULTS[text_doc.uri] = (ast, tuple(diagnostics))

    return diagnostics


def parse_function(
    mecha: Mecha, function: TextFileBase[Any] | list[str] | str
) -> AstRoot:
    if not isinstance(function, TextFileBase):
        function = Function(function)

    stream = TokenStream(
        source=function.text,
        preprocessor=mecha.preprocessor,
    )

    mecha.database.current = function
    mecha.database[function] = CompilationUnit(resource_location="lsp:current")

    ast = mecha.parse_stream(mecha.spec.multiline, None, AstRoot.parser, stream)
    return ast
