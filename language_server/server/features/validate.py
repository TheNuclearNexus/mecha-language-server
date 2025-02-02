from contextlib import contextmanager
from dataclasses import dataclass
from functools import partial
import logging
import os
import traceback
from pathlib import PurePath
from typing import Any, TypeVar

from beet import Context, DataPack, Function, NamespaceFile, PackLoadUrl, TextFileBase
from beet.core.utils import required_field, extra_field
from bolt import Module, Runtime
from mecha import (
    AbstractNode,
    AstChildren,
    AstNode,
    AstRoot,
    CompilationUnit,
    Diagnostic,
    DiagnosticCollection,
    Dispatcher,
    Mecha,
    MutatingReducer,
    rule,
)
from mecha.contrib.nested_location import (
    NestedLocationTransformer,
    NestedLocationResolver,
)
from mecha.ast import AstError
from pygls.workspace import TextDocument
from tokenstream import InvalidSyntax, TokenStream

from ..indexing import Indexer, ProjectIndex
from ..shadows.compile_document import (
    COMPILATION_RESULTS,
    CompiledDocument,
    CompilationError
)
from ..shadows.context import LanguageServerContext

SUPPORTED_EXTENSIONS = [Function.extension, Module.extension]
T = TypeVar("T", bound=AstNode)


def get_compilation_data(ctx: LanguageServerContext, text_doc: TextDocument):
    resource = ctx.path_to_resource.get(text_doc.path)

    if resource and resource[0] in COMPILATION_RESULTS:
        return COMPILATION_RESULTS[resource[0]]

    validate_function(ctx, text_doc)

    resource = resource or ctx.path_to_resource.get(text_doc.path)

    if resource is None:
        return None

    # logging.debug(COMPILATION_RESULTS)
    return COMPILATION_RESULTS[resource[0]]


def validate_function(
    ctx: LanguageServerContext, text_doc: TextDocument
) -> list[CompilationError]:

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
    
    compiled_doc = parse_function(
        ctx, location, text_doc.path, type(file)(text_doc.source, text_doc.path)
    )

    COMPILATION_RESULTS[location] = compiled_doc

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


@dataclass
class ErrorAccumulator(MutatingReducer):
    _errors: list[InvalidSyntax] = extra_field(default_factory=list)
    resource_location: str = required_field()
    filename: str | None = required_field()
    file_instance: TextFileBase[Any] = required_field()

    @rule(AstError)
    def error(self, error: AstError):

        self._errors.append(error.error)

        return None

    def collect(self, root: T | None) -> tuple[T | None, list[InvalidSyntax]]:
        if root is None:
            return (root, [])

        root = self.__call__(root)

        return (root, self._errors)


Node = TypeVar("Node", bound=AbstractNode)


def parse_function(
    ctx: LanguageServerContext,
    resource_location: str,
    source_path: str,
    file_instance: Function | Module,
) -> CompiledDocument:

    ast, errors = compile(ctx, resource_location, source_path, file_instance)


    # # Parse the stream
    mecha = ctx.inject(Mecha)
    compilation_unit = mecha.database[file_instance]
    runtime = ctx.inject(Runtime)
    compiled_module = runtime.modules.registry.get(file_instance)

    return CompiledDocument(
        resource_location=resource_location,
        ast=ast,
        diagnostics=[*errors, *compilation_unit.diagnostics.exceptions],
        compiled_unit=compilation_unit,
        compiled_module=compiled_module,
        ctx=ctx,
        dependents=set(),
    )

@contextmanager
def use_steps(mecha: Mecha, steps):
    initial_steps = mecha.steps 
    mecha.steps = steps
    yield 
    mecha.steps = initial_steps

def compile(
    ctx: LanguageServerContext,
    resource_location: str,
    source_path: str,
    source_file: Function | Module,
) -> tuple[AstRoot, list[InvalidSyntax]]:
    mecha = ctx.inject(Mecha)
    diagnostics = []

    indexer = Indexer(
        ctx=ctx,
        resource_location=resource_location,
        source_path=source_path,
        file_instance=source_file,
    )

    with use_steps(mecha, [indexer, *mecha.steps]):
        mecha.database.setup_compilation()

        # Configure the database to compile the file
        compiled_unit = CompilationUnit(resource_location=resource_location, pack=ctx.data)
        mecha.database[source_file] = compiled_unit
        mecha.database.enqueue(source_file)

        for step, file_instance in mecha.database.process_queue():
            compilation_unit = mecha.database[file_instance]

            if step < 0:
                try:
                    compilation_unit.source = file_instance.text
                    # Create the token stream
                    stream = TokenStream(
                        source=compilation_unit.source,
                        preprocessor=mecha.preprocessor,
                    )

                    ast = mecha.parse_stream(
                        mecha.spec.multiline, None, AstRoot.parser, stream  # type: ignore
                    )

                    ast, errors = ErrorAccumulator(
                        resource_location=resource_location,
                        filename=compilation_unit.filename,
                        file_instance=file_instance,
                    ).collect(ast)

                    diagnostics.extend(errors)

                    compilation_unit.ast = ast
                    mecha.database.enqueue(file_instance, 0)

                except InvalidSyntax as exec:
                    logging.error(f"Failed to parse: {exec}")
                except KeyError as exec:
                    tb = "\n".join(traceback.format_tb(exec.__traceback__))
                    logging.error(f"{tb}")
                except Exception as exec:
                    logging.error(f"{type(exec)}: {exec}")

            elif step < len(mecha.steps):
                if not compilation_unit.ast:
                    continue
                step_diagnostics = DiagnosticCollection()
                try:
                    with mecha.steps[step].use_diagnostics(step_diagnostics):
                        if ast := mecha.steps[step](compilation_unit.ast):
                            if not step_diagnostics.error:
                                compilation_unit.ast = ast
                                mecha.database.enqueue(
                                    key=file_instance,
                                    step=step + 1,
                                    priority=compilation_unit.priority,
                                )

                            compilation_unit.diagnostics.extend(step_diagnostics)
                except Exception as e:
                    tb = "\n".join(traceback.format_tb(e.__traceback__))
                    logging.error(f"{type(e)} {e}\n{tb}")

    return indexer.output_ast, diagnostics
