from contextlib import ExitStack, contextmanager
from copy import deepcopy
from dataclasses import dataclass
import json
import logging
import sys
from typing import Iterator, List
from urllib import request
from beet import (
    Context,
    GenericPlugin,
    NamespaceFile,
    PluginSpec,
    Project,
    ProjectBuilder,
    ProjectConfig,
    Task,
    load_config,
    PluginError,
    Pipeline,
)
from beet.library.base import LATEST_MINECRAFT_VERSION
from beet.toolchain.template import TemplateManager
from beet.core.utils import (
    normalize_string,
    change_directory,
    local_import_path,
    required_field
)

from beet.contrib.load import load

from bolt import CompiledModule
from mecha import AstNode, CompilationUnit, Mecha, DiagnosticErrorSummary
from pygls.server import LanguageServer
from pygls.workspace import TextDocument
from lsprotocol import types as lsp
import os

from pathlib import Path
from urllib.parse import unquote, urlparse
from urllib.request import url2pathname

from tokenstream import InvalidSyntax


logging.basicConfig(filename="mecha.log", filemode="w", level=logging.DEBUG)

CONFIG_TYPES = ["beet.json", "beet.yaml", "beet.yml"]
COMPILATION_RESULTS: dict[str, "CompiledDocument"] = {}
PATH_TO_RESOURCE: dict[str, tuple[str, NamespaceFile]] = {}
GAME_REGISTRIES: dict[str, list[str]] = {}

@dataclass
class CompiledDocument:
    ctx: Context 
    
    resource_location: str

    ast: AstNode | None
    diagnostics: list[InvalidSyntax]

    compiled_unit: CompilationUnit | None
    compiled_module: CompiledModule | None


class PipelineShadow(Pipeline):
    def require(self, *args: GenericPlugin[Context] | str):
        for spec in args:
            plugin = self.resolve(spec)
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
    ls: "MechaLanguageServer" = required_field()

    def require(self, *args: PluginSpec):
        """Execute the specified plugin."""
        for arg in args:
            try:
                self.inject(PipelineShadow).require(arg)
            except PluginError as exc:
                self.ls.show_message(f"Failed to load plugin: {arg}\n{exc}", lsp.MessageType.Error)
                
    @contextmanager
    def activate(self):
        """Push the context directory to sys.path and handle cleanup to allow module reloading."""
        with local_import_path(str(self.directory.resolve())), self.cache:
            yield self.inject(PipelineShadow)


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
    @contextmanager
    def build(self, ls: "MechaLanguageServer") -> Iterator[LanguageServerContext]:
        """Create the context, run the pipeline, and return the context."""
        with ExitStack() as stack:
            name = self.config.name or self.project.directory.stem
            meta = deepcopy(self.config.meta)

            tmpdir = None
            cache = self.project.cache

            ctx = LanguageServerContext(
                ls=ls,
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

            yield ctx



class MechaLanguageServer(LanguageServer):
    instances: dict[Path, Context] = dict()
    _sites: list[str] = []

    def set_sites(self, sites: list[str]):
        self._sites = sites

    def __init__(self, *args):
        super().__init__(*args)
        self.instances = {}
    
    def load_registry(self, minecraft_version: str):
        """Load the game registry from Misode's mcmeta repository"""
        global GAME_REGISTRIES

        if len(minecraft_version) <= 0:
            minecraft_version = LATEST_MINECRAFT_VERSION

        cache_dir = Path("./.mls_cache")
        if not cache_dir.exists():
            os.mkdir(cache_dir)
        
        if not (cache_dir / "registries").exists():
            os.mkdir(cache_dir / "registries")

        file_path = cache_dir / "registries" / (minecraft_version + ".json")

        logging.debug(minecraft_version)

        if not file_path.exists():
            try:
                request.urlretrieve(f"https://raw.githubusercontent.com/misode/mcmeta/refs/tags/{minecraft_version}-summary/registries/data.min.json", file_path)
            except Exception as exc: 
                self.show_message(f"Failed to download registry for version {minecraft_version}, completions will be disabled\n{exc}", lsp.MessageType.Error)
                
                return

        with open(file_path) as file:
            try:
                registries = json.loads(file.read())
                for k in registries:
                    GAME_REGISTRIES[k] = registries[k]     

            except json.JSONDecodeError as exc:
                self.show_message(f"Failed to parse registry for version {minecraft_version}, completions will be disabled\n{exc}", lsp.MessageType.Error)
                os.remove(file_path)

            except Exception as exc:
                self.show_message(f"An unhandled exception occured loading registry for version {minecraft_version}\n{exc}", lsp.MessageType.Error)
                os.remove(file_path)


    def create_context(self, config: ProjectConfig, config_path: Path) -> Context: 
        """Attempt to configure the project's context and run necessary plugins"""
        project = Project(config, None, config_path)
        with ProjectBuilderShadow(project, root=True).build(self) as ctx:
            mc = ctx.inject(Mecha)        

            logging.debug(f"Mecha created for {config_path} successfully")

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
                        PATH_TO_RESOURCE[str(path)] = (location, file)
                    except:
                        continue

            return ctx
        return None

            
    def create_instance(
        self, config_path: Path
    ) -> Context | None:
        config = load_config(config_path)
        logging.debug(config)
        # Ensure that we aren't loading in all project files
        config.output = None

        config.pipeline = list(filter(lambda p: isinstance(p, str), config.pipeline))

        og_cwd = os.getcwd()
        og_sys_path = sys.path
        og_modules = sys.modules

        sys.path = [*self._sites, str(config_path.parent), *og_sys_path]

        os.chdir(config_path.parent)


        instance = None

        try:
            instance = self.create_context(config, config_path)

        except PluginError as plugin_error:
            logging.error(plugin_error.__cause__)
            raise plugin_error.__cause__
        except DiagnosticErrorSummary as summary:
            logging.error("Errors found in the following:")
            for diag in summary.diagnostics.exceptions:
                logging.error("\t" + str(diag.file.source_path if diag.file is not None else ""))

        except Exception as e:
            logging.error(f"Error occured while running beet: {type(e)} {e}")

        os.chdir(og_cwd)
        sys.path = og_sys_path
        sys.modules = og_modules

        self.load_registry(config.minecraft)

        return instance

    def setup_workspaces(self):
        config_paths: list[Path] = []

        for w in self.workspace.folders.values():
            ws_path = self.uri_to_path(w.uri)

            for config_type in CONFIG_TYPES:
                for config_path in ws_path.glob("**/" + config_type):
                    config_paths.append(config_path)
                    logging.debug(config_path)

        self.instances = { # type: ignore
            c.parent: self.create_instance(c) for c in config_paths
        }
        # logging.debug(self.mecha_instances)

    def uri_to_path(self, uri: str):
        parsed = urlparse(uri)
        host = "{0}{0}{mnt}{0}".format(os.path.sep, mnt=parsed.netloc)
        norm_path = os.path.normpath(
            os.path.join(host, url2pathname(unquote(parsed.path)))
        )
        # logging.debug(norm_path)
        norm_path = Path(norm_path)
        return norm_path
    
    def get_instance(self, config_path: Path):
        if config_path not in self.instances or self.instances[config_path] is None:
            instance = self.create_instance(config_path)

            if instance is not None:
                self.instances[config_path] = instance

            return instance
        else:
            return self.instances[config_path]

    def get_context(self, document: TextDocument):
        doc_path = Path(document.path)

        parents: list[Path] = []

        for parent_path in self.instances.keys():
            if doc_path.is_relative_to(parent_path):
                parents.append(parent_path)

        parents = sorted(parents, key=lambda p: len(str(p).split(os.path.sep)))
        # logging.debug(parents[-1])
        instance = self.get_instance(parents[-1])

        return instance
