from contextlib import ExitStack, contextmanager
from copy import deepcopy
from dataclasses import dataclass
import os
from typing import Any, Callable, Iterator, List, cast
from beet import (
    Context,
    GenericPlugin,
    NamespaceFile,
    PluginSpec,
    ProjectBuilder,
    ProjectConfig,
    Task,
    PluginError,
    Pipeline,
)
from beet.library.base import LATEST_MINECRAFT_VERSION
from beet.toolchain.template import TemplateManager
from beet.core.utils import (
    normalize_string,
    change_directory,
    local_import_path,
    required_field,
    extra_field
)

from beet.contrib.load import load

from bolt import CompiledModule
from mecha import AstNode, CompilationUnit, Mecha
from lsprotocol import types as lsp
from pygls.server import LanguageServer


from tokenstream import InvalidSyntax

COMPILATION_RESULTS: dict[str, "CompiledDocument"] = {}

@dataclass
class CompiledDocument:
    ctx: "LanguageServerContext"

    resource_location: str

    ast: AstNode | None
    diagnostics: list[InvalidSyntax]

    compiled_unit: CompilationUnit | None
    compiled_module: CompiledModule | None

    dependents: set[str] = extra_field(default_factory=set)


class PipelineShadow(Pipeline):
    def require(self, *args: GenericPlugin[Context] | str):
        for spec in args:
            try:
                plugin = self.resolve(spec)
            except Exception as exc:
                ls = cast(LanguageServerContext, self.ctx).ls
                message = f"An issue occured while loading plugin: {spec}\n{exc}"
                ls.show_message(message.split("\n")[0], lsp.MessageType.Warning)
                ls.show_message_log(message, lsp.MessageType.Warning)
                continue

            if plugin in self.plugins:
                continue

            self.plugins.add(plugin)

            # Advance the plugin only once, ignore remaining work
            # Most setup happens in the first half of the plugin
            # where side effects happen in the latter
            Task(plugin).advance(self.ctx)


# We use this shadow of context in order to route calls to `ctx`
# to our own methods, this allows us to bypass side effects without
# having to break plugins
@dataclass(frozen=True)
class LanguageServerContext(Context):
    ls: LanguageServer = required_field()
    project_config: ProjectConfig = required_field()

    path_to_resource: dict[str, tuple[str, NamespaceFile]] = extra_field(default_factory=dict)


    def require(self, *args: PluginSpec):
        """Execute the specified plugin."""
        for arg in args:
            try:
                self.inject(PipelineShadow).require(arg)
            except PluginError as exc:
                message = f"Failed to load plugin: {arg}\n{exc}"
                self.ls.show_message(message.split("\n")[0], lsp.MessageType.Error)
                self.ls.show_message_log(message, lsp.MessageType.Error)
                
    @contextmanager
    def activate(self):
        """Push the context directory to sys.path and handle cleanup to allow module reloading."""
        with local_import_path(str(self.directory.resolve())), self.cache:
            yield self.inject(PipelineShadow)


    def get_resource_from_path(self, path: str) -> tuple[str, NamespaceFile] | None:
        return self.path_to_resource.get(path)


def get_excluded_plugins(ctx: Context):
    lsp_config: dict = ctx.meta.setdefault("lsp", {})
    
    excluded_plugins = lsp_config.get("excluded_plugins") or []

    return excluded_plugins

class ProjectBuilderShadow(ProjectBuilder):
    def bootstrap(self, ctx: Context):
        """Plugin that handles the project configuration."""

        excluded_plugins = get_excluded_plugins(ctx)
        plugins = self.config.require

        for plugin in plugins:
            if plugin in excluded_plugins:
                continue

            ctx.require(plugin)

    # This stripped down version of build only handles loading the plugins from config
    # all other operations are gone such as linking
    def initialize(self, ls: LanguageServer) -> LanguageServerContext:
        """Create the context, run the pipeline, and return the context."""
        with ExitStack() as stack:
            name = self.config.name or self.project.directory.stem
            meta = deepcopy(self.config.meta)

            tmpdir = None
            cache = self.project.cache

            ctx = LanguageServerContext(
                ls=ls,
                project_config=self.config,
                project_id=self.config.id or normalize_string(name),
                project_name=name,
                project_description=self.config.description,
                project_author=self.config.author,
                project_version=self.config.version,
                project_root=self.root,
                minecraft_version=self.config.minecraft if len(self.config.minecraft) > 0 else LATEST_MINECRAFT_VERSION,
                directory=self.project.directory,
                output_directory=self.project.output_directory,
                meta=meta,
                cache=cache,
                worker=stack.enter_context(self.project.worker_pool.handle()),
                template=TemplateManager(
                    templates=self.project.template_directories,
                    cache_dir=cache["template"].directory,
                ),
                whitelist=self.config.whitelist,
            )

            

            pipelined_plugin: List[PluginSpec] = [self.bootstrap]


            excluded_plugins = get_excluded_plugins(ctx)
            for item in self.config.pipeline:
                if item == "mecha" or not isinstance(item, str) or item in excluded_plugins:
                    continue

                pipelined_plugin.append(item)

            with change_directory(tmpdir):
                for plugin in pipelined_plugin:
                    ctx.require(plugin)
                # pipeline = stack.enter_context(ctx.activate())
                # pipeline.run(plugins)
            
            # Load everything into context *after* the first half of the plugins
            # are ran by the pipeline
            load(
                resource_pack=self.config.resource_pack.load,
                data_pack=self.config.data_pack.load,
            )(ctx)

            mc = ctx.inject(Mecha)
        
            for pack in ctx.packs:
                # Load all files into the compilation database
                for provider in mc.providers:
                    for file_instance, compilation_unit in provider(pack, mc.match):
                        mc.database[file_instance] = compilation_unit
                        mc.database.enqueue(file_instance)

                # Build a map of file path to resource location
                for location, file in pack.all():
                    try:
                        path = os.path.normpath(file.ensure_source_path())
                        path = os.path.normcase(path)
                        ctx.path_to_resource[str(path)] = (location, file)
                    except:
                        continue

            return ctx

