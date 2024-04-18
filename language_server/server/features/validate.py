from lsprotocol import types as lsp
from mecha.ast import AstError
from tokenstream import InvalidSyntax, UnexpectedToken

from .. import MechaLanguageServer


def validate(ls: MechaLanguageServer, params: lsp.DidOpenTextDocumentParams):
    text_doc = ls.workspace.get_document(params.text_document.uri)

    diagnostics = validate_function(ls, text_doc.source)

    ls.publish_diagnostics(
        params.text_document.uri,
        [
            tokenstream_error_to_lsp_diag(d, type(ls).__name__, text_doc.filename)
            for d in diagnostics
        ],
    )


def tokenstream_error_to_lsp_diag(
    exec: InvalidSyntax, source: str, filename: str
) -> lsp.Diagnostic:
    return lsp.Diagnostic(
        range=lsp.Range(
            start=lsp.Position(
                line=exec.location.lineno - 1, character=exec.location.colno - 1
            ),
            end=lsp.Position(
                line=exec.end_location.lineno - 1, character=exec.end_location.colno - 1
            ),
        ),
        message=f"{type(exec).__name__}\n{exec.format(filename)}",
        source=source,
    )


def validate_function(
    ls: MechaLanguageServer, source: str
) -> list[InvalidSyntax]:
    diagnostics = []
    try:
        ast = ls.mecha.parse_function(source)
    except InvalidSyntax as exec:
        ls.send_notification("Failed to parse")
        diagnostics.append(exec)

    else:
        for node in ast.walk():
            if isinstance(node, AstError):
                diagnostics.append(node.error)

    return diagnostics
