from lsprotocol import types as lsp
from mecha.ast import AstError
from tokenstream import InvalidSyntax, UnexpectedToken

from .. import MechaLanguageServer


def validate(ls: MechaLanguageServer, params: lsp.DidChangeTextDocumentParams):
    ls.show_message("Validating function...")

    text_doc = ls.workspace.get_document(params.text_document.uri)

    diagnostics = validate_function(ls, text_doc.source, text_doc.filename)

    ls.publish_diagnostics(params.text_document.uri, diagnostics)


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
        message=exec.format(filename),
        source=source,
    )


def validate_function(ls: MechaLanguageServer, source: str, filename: str | None):
    diagnostics = []
    try:
        ast = ls.mecha.parse_function(source)
    except InvalidSyntax as exec:
        diagnostics.append(
            tokenstream_error_to_lsp_diag(exec, type(ls).__name__, filename)
        )

    else:
        for node in ast.walk():
            if isinstance(node, AstError):
                diagnostics.append(
                    tokenstream_error_to_lsp_diag(
                        node.error, type(ls).__name__, filename
                    )
                )

    return diagnostics
