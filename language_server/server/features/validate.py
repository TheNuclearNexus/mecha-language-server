import logging
import os
import traceback
from dataclasses import dataclass
from pathlib import Path, PurePath
from typing import Any

from beet import Context, DataPack, Function, PackageablePath, PackLoadUrl, TextFileBase
from beet.contrib.load import load
from bolt import CompiledModule, Module, Runtime
from lsprotocol import types as lsp
from mecha import AstChildren, AstNode, AstRoot, CompilationUnit, Mecha
from mecha.ast import AstError
from pygls.workspace import TextDocument
from tokenstream import InvalidSyntax, TokenStream, UnexpectedToken

from language_server.server.indexing import Bindings, index_function_ast
from language_server.server.shadows import (
    COMPILATION_RESULTS,
    CompiledDocument,
    LanguageServerContext,
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

    # logging.debug(f"Sending diagnostics: {diagnostics}")

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
    # logging.debug(trace)

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
    resource = ctx.path_to_resource.get(text_doc.path)
    
    if resource and resource[0] in COMPILATION_RESULTS:
        return COMPILATION_RESULTS[resource[0]]

    validate_function(ls, ctx, text_doc)

    resource = resource or ctx.path_to_resource.get(text_doc.path)

    if resource is None:
        return None

    # logging.debug(COMPILATION_RESULTS)
    return COMPILATION_RESULTS[resource[0]]


def validate_function(
    ls: MechaLanguageServer, ctx: LanguageServerContext, text_doc: TextDocument
) -> list[InvalidSyntax]:
    # logging.debug(f"Parsing function:\n{text_doc.source}")

    path = os.path.normcase(os.path.normpath(text_doc.path))

    if path not in ctx.path_to_resource:
        if not try_to_mount_file(ctx, path):
            return []

    location, file = ctx.path_to_resource[path]

    if not isinstance(file, Function) and not isinstance(file, Module):
        COMPILATION_RESULTS[location] = CompiledDocument(
            ctx, location, None, [], None, None
        )
        return []

    # file.text = text_doc.source

    # file.set_content(text_doc.source)

    compiled_doc = parse_function(
        ctx, location, type(file)(text_doc.source, text_doc.path)
    )

    COMPILATION_RESULTS[location] = compiled_doc
    # logging.debug(COMPILATION_RESULTS)
    return compiled_doc.diagnostics


def try_to_mount_file(ctx: LanguageServerContext, file_path: str):
    """Try to mount a given file path to the context. True if the file was successfully mounted"""

    _, file_extension = os.path.splitext(file_path)
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
                    # File can't be relative to a url
                    if isinstance(path, PackLoadUrl):
                        continue

                    if PurePath(file_path).is_relative_to(path):
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

    # Create the token stream
    stream = TokenStream(
        source=function.text,
        preprocessor=mecha.preprocessor,
    )

    # Configure the database to compile the file
    mecha.database.current = function
    compiled_unit = CompilationUnit(resource_location=location, pack=ctx.data)
    mecha.database[function] = compiled_unit

    diagnostics = []

    # Parse the stream
    ast = AstRoot(commands=AstChildren())
    try:
        ast: AstNode = mecha.parse_stream(
            mecha.spec.multiline, None, AstRoot.parser, stream  # type: ignore
        )

        for node in ast.walk():
            if isinstance(node, AstError):
                diagnostics.append(node.error)
    except InvalidSyntax as exec:
        logging.error(f"Failed to parse: {exec}")
        diagnostics.append(exec)
    except KeyError as exec:
        tb = "\n".join(traceback.format_tb(exec.__traceback__))
        logging.error(f"{tb}")
    except Exception as exec:
        logging.error(f"{type(exec)}: {exec}")

    dependents = set()


    compiled_module = None
    runtime = ctx.inject(Runtime)
    if location in COMPILATION_RESULTS:
        prev_compilation = COMPILATION_RESULTS[location]
        dependents = prev_compilation.dependents
        compiled_module = prev_compilation.compiled_module

    if len(diagnostics) == 0 and Module in ctx.data.extend_namespace:

        if fresh_module := runtime.modules.get(function):
            fresh_module.ast = index_function_ast(
                fresh_module.ast, location, mecha, runtime, fresh_module
            )

            for dependency in fresh_module.dependencies:
                if dependency in COMPILATION_RESULTS:
                    COMPILATION_RESULTS[dependency].dependents.add(location)

            compiled_module = fresh_module

    ast = index_function_ast(
        ast, location, mecha, runtime=runtime, module=compiled_module
    )

    for dependent in dependents:
        if not dependent in COMPILATION_RESULTS:
            continue

        parse_function(
            ctx,
            dependency,
            ctx.data.functions[dependent] or ctx.data[Module][dependent],
        )
        del COMPILATION_RESULTS[dependency]

    return CompiledDocument(
        resource_location=location,
        ast=ast,
        diagnostics=diagnostics,
        compiled_unit=compiled_unit,
        compiled_module=compiled_module,
        ctx=ctx,
        dependents=dependents,
    )
