from dataclasses import dataclass
import logging
import os
from pathlib import Path, PurePath
import traceback
from typing import Any
from beet import Context, DataPack, Function, PackLoadUrl, PackageablePath, TextFileBase
from beet.contrib.load import load
from bolt import CompiledModule, Module, Runtime
from lsprotocol import types as lsp
from mecha import AstChildren, AstNode, AstRoot, CompilationUnit, Mecha
from mecha.ast import AstError
from tokenstream import InvalidSyntax, TokenStream, UnexpectedToken
from pygls.workspace import TextDocument

from language_server.server.indexing import MetaDataAttacher, index_function_ast
from language_server.server.shadows import (
    LanguageServerContext,
    CompiledDocument,
    COMPILATION_RESULTS,
)

from .. import MechaLanguageServer


SUPPORTED_EXTENSIONS = [Function.extension, Module.extension]


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


def get_compilation_data(
    ls: MechaLanguageServer, ctx: LanguageServerContext, text_doc: TextDocument
):
    if text_doc.uri in COMPILATION_RESULTS:
        return COMPILATION_RESULTS[text_doc.uri]

    validate_function(ls, ctx, text_doc)
    return COMPILATION_RESULTS[text_doc.uri]


def validate_function(
    ls: MechaLanguageServer, ctx: LanguageServerContext, text_doc: TextDocument
) -> list[InvalidSyntax]:
    logging.debug(f"Parsing function:\n{text_doc.source}")

    path = os.path.normcase(os.path.normpath(text_doc.path))

    if path not in ctx.path_to_resource:
        if not try_to_mount_file(ctx, path):
            COMPILATION_RESULTS[text_doc.uri] = CompiledDocument(
                ctx, "", None, [], None, None
            )
            return []
            

    location, file = ctx.path_to_resource[path]

    if not isinstance(file, Function) and not isinstance(file, Module):
        COMPILATION_RESULTS[text_doc.uri] = CompiledDocument(
            ctx, location, None, [], None, None
        )
        return []

    # file.text = text_doc.source

    # file.set_content(text_doc.source)

    compiled_doc = parse_function(
        ctx, location, type(file)(text_doc.source, text_doc.path)
    )

    COMPILATION_RESULTS[text_doc.uri] = compiled_doc

    return compiled_doc.diagnostics


def try_to_mount_file(ctx: LanguageServerContext, file_path: str):
    """Try to mount a given file path to the context. True if the file was successfully mounted"""

    _, file_extension = os.path.splitext(file_path)
    logging.debug(f"\n\nTry to mount {file_path}, {file_extension}\n\n")
    if not file_extension in SUPPORTED_EXTENSIONS:
        return False

    load_options = ctx.project_config.data_pack.load
    prefix = None
    for entry in load_options.entries():
        # File can't be relative to a url
        if isinstance(entry, PackLoadUrl):
            continue

        if isinstance(entry, dict):
            for key, paths in entry.items():
                for path in paths.entries():
                    logging.debug(f"\n\n{path}")
                    # File can't be relative to a url
                    if isinstance(path, PackLoadUrl):
                        continue

                    if PurePath(file_path).is_relative_to(path):
                        logging.debug('was relative too')
                        relative = PurePath(file_path).relative_to(path)
                        prefix = str(key / relative)
                        break
        elif PurePath(file_path).is_relative_to(entry):
            relative = PurePath(file_path).relative_to(entry)
            prefix = str(relative)
        
    if prefix == None:
        return False

    try:
        temp = DataPack()
        temp.mount(prefix, file_path)
        for [location, file] in temp.all():
            if not (isinstance(file, Function) or isinstance(file, Module)):
                continue

            path = os.path.normpath(file.ensure_source_path())
            path = os.path.normcase(path)
            ctx.path_to_resource[path] = (location, file)
            ctx.data[type(file)][location] = file

        return True
    except Exception as exc:
        logging.error(f"Failed to mount {path}, reloading datapack,\n{exc}")

    return False


def parse_function(
    ctx: LanguageServerContext, location: str, function: Function | Module
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

    ast = index_function_ast(ast, location)
    for node in ast.walk():
        if isinstance(node, AstError):
            diagnostics.append(node.error)

    if len(diagnostics) == 0 and Module in ctx.data.extend_namespace:
        runtime = ctx.inject(Runtime)
        compiled_module = runtime.modules.get(function)

        if compiled_module is not None:
            compiled_module.ast = index_function_ast(compiled_module.ast, location)
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
