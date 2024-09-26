from dataclasses import dataclass
import logging
import os
import traceback
from typing import Any
from beet import Context, Function, TextFileBase
from bolt import CompiledModule, Module, Runtime
from lsprotocol import types as lsp
from mecha import AstChildren, AstNode, AstRoot, CompilationUnit, Mecha
from mecha.ast import AstError
from tokenstream import InvalidSyntax, TokenStream, UnexpectedToken
from pygls.workspace import TextDocument

from language_server.server.indexing import Indexer

from .. import (
    COMPILATION_RESULTS,
    PATH_TO_RESOURCE,
    CompiledDocument,
    MechaLanguageServer,
)


def validate(
    ls: MechaLanguageServer,
    params: lsp.DidOpenTextDocumentParams | lsp.DidChangeTextDocumentParams,
):
    text_doc = ls.workspace.get_document(params.text_document.uri)
    ctx = ls.get_context(text_doc)

    if not ctx:
        diagnostics = []
    else:
        diagnostics = validate_function(ls, ctx, text_doc)
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
    exec: InvalidSyntax, source: str, filename: str | None
) -> lsp.Diagnostic:
    range = [exec.location, exec.end_location]
    if isinstance(exec, UnexpectedToken):
        range = [exec.token.location, exec.token.end_location]

    trace = "\n".join(traceback.format_tb(exec.__traceback__))
    logging.debug(trace)

    return lsp.Diagnostic(
        range=lsp.Range(
            start=lsp.Position(line=range[0].lineno - 1, character=range[0].colno - 1),
            end=lsp.Position(line=range[1].lineno - 1, character=range[1].colno - 1),
        ),
        message=f"{exec.format(filename if filename is not None else 'file')}\n{type(exec).__name__}",  # \n{exec.format(filename)}\n\n{trace}
        source=source,
    )


def get_compilation_data(ls: MechaLanguageServer, ctx: Context, text_doc: TextDocument):
    if text_doc.uri in COMPILATION_RESULTS:
        return COMPILATION_RESULTS[text_doc.uri]

    validate_function(ls, ctx, text_doc)
    return COMPILATION_RESULTS[text_doc.uri]


def validate_function(
    ls: MechaLanguageServer, ctx: Context, text_doc: TextDocument
) -> list[InvalidSyntax]:
    logging.debug(f"Parsing function:\n{text_doc.source}")

    path = os.path.normcase(os.path.normpath(text_doc.path))

    if path not in PATH_TO_RESOURCE:
        COMPILATION_RESULTS[text_doc.uri] = CompiledDocument(
            ctx, "", None, [], None, None
        )
        return []

    location, file = PATH_TO_RESOURCE[path]

    if not isinstance(file, Function) and not isinstance(file, Module):
        COMPILATION_RESULTS[text_doc.uri] = CompiledDocument(
            ctx, location, None, [], None, None
        )
        return []
    
    # file.text = text_doc.source

    # file.set_content(text_doc.source)

    compiled_doc = parse_function(ctx, location, type(file)(text_doc.source, text_doc.path))

    COMPILATION_RESULTS[text_doc.uri] = compiled_doc

    return compiled_doc.diagnostics


def parse_function(
    ctx: Context, location: str, function: Function | Module
) -> CompiledDocument:
    mecha = ctx.inject(Mecha)

    stream = TokenStream(
        source=function.text,
        preprocessor=mecha.preprocessor,
    )

    mecha.database.current = function
    compiled_unit = CompilationUnit(resource_location=location, pack=ctx.data)
    mecha.database[function] = compiled_unit

    diagnostics = []

    ast = AstRoot(commands=AstChildren())
    try:
        ast: AstNode = mecha.parse_stream(
            mecha.spec.multiline, None, AstRoot.parser, stream  # type: ignore
        )
    except InvalidSyntax as exec:
        logging.error(f"Failed to parse: {exec}")
        diagnostics.append(exec)
    except KeyError as exec:
        tb = "\n".join(traceback.format_tb(exec.__traceback__))
        logging.error(f"{tb}")
    except Exception as exec:
        logging.error(f"{type(exec)}: {exec}")

    indexer = Indexer()

    ast = indexer(ast)
    for node in ast.walk():
        if isinstance(node, AstError):
            diagnostics.append(node.error)

    if len(diagnostics) == 0:
        runtime = ctx.inject(Runtime)
        compiled_module = runtime.modules.get(function)

        if compiled_module is not None:
            compiled_module.ast = indexer(compiled_module.ast)
            logging.debug(compiled_module)
    else:
        compiled_module = None

    return CompiledDocument(
        resource_location=location,
        ast=ast,
        diagnostics=diagnostics,
        compiled_unit=compiled_unit,
        compiled_module=compiled_module,
        ctx=ctx,
    )
