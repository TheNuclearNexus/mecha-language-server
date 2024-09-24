from contextlib import ExitStack, contextmanager
from copy import deepcopy
import logging
import sys
from typing import Iterator, List
from beet import (
    Context,
    GenericPlugin,
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
)

from beet.contrib.load import load

from mecha import AstRoot, Mecha, DiagnosticErrorSummary
from pygls.server import LanguageServer
from pygls.workspace import TextDocument
import os

from pathlib import Path
from urllib.parse import unquote, urlparse
from urllib.request import url2pathname

from tokenstream import InvalidSyntax

logging.basicConfig(filename="mecha.log", filemode="w", level=logging.DEBUG)

CONFIG_TYPES = ["beet.json", "beet.yaml", "beet.yml"]
COMPILATION_RESULTS: dict[str, tuple[AstRoot, tuple[InvalidSyntax]]] = {}


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
            logging.debug(f"Advanced {plugin}")
            Task(plugin).advance(self.ctx)


# We use this shadow of context in order to route calls to `ctx`
# to our own methods, this allows us to bypass side effects without
# having to break plugins
class ContextShadow(Context):
    def require(self, *args: PluginSpec):
        """Execute the specified plugin."""
        self.inject(PipelineShadow).require(*args)

    @contextmanager
    def activate(self):
        """Push the context directory to sys.path and handle cleanup to allow module reloading."""
        with local_import_path(str(self.directory.resolve())), self.cache:
            yield self.inject(PipelineShadow)


class ProjectBuilderShadow(ProjectBuilder):
    def bootstrap(self, ctx: Context):
        """Plugin that handles the project configuration."""
        plugins = self.config.require

        for plugin in plugins:
            ctx.require(plugin)

    # This stripped down version of build only handles loading the plugins from config
    # all other operations are gone such as linking
    @contextmanager
    def build(self) -> Iterator[Context]:
        """Create the context, run the pipeline, and return the context."""
        with ExitStack() as stack:
            name = self.config.name or self.project.directory.stem
            meta = deepcopy(self.config.meta)

            tmpdir = None
            cache = self.project.cache

            ctx = ContextShadow(
                project_id=self.config.id or normalize_string(name),
                project_name=name,
                project_description=self.config.description,
                project_author=self.config.author,
                project_version=self.config.version,
                project_root=self.root,
                minecraft_version=self.config.minecraft or LATEST_MINECRAFT_VERSION,
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

            for item in self.config.pipeline:

                if item == "mecha" or not isinstance(item, str):
                    continue

                logging.debug(f"Adding pipline {item}")
                pipelined_plugin.append(item)

            with change_directory(tmpdir):
                for plugin in pipelined_plugin:
                    logging.debug(f"running pipeline: {plugin}")
                    ctx.require(plugin)
                # pipeline = stack.enter_context(ctx.activate())
                # pipeline.run(plugins)
            
            # Load everything into context *after* the first half of the plugins
            # are ran by the pipeline
            load(
                resource_pack=self.config.resource_pack.load,
                data_pack=self.config.data_pack.load,
            )(ctx)

            logging.debug(ctx.data.extend_namespace)
            for type in ctx.data.extend_namespace:
                logging.debug(ctx.data[type])
            
            yield ctx


def create_context(config: ProjectConfig, config_path: Path) -> Context: 
    project = Project(config, None, config_path)
    with ProjectBuilderShadow(project, root=True).build() as ctx:
        mc = ctx.inject(Mecha)

        # for mod in ctx.data[Module]:
        #     logging.debug(mod)

        logging.debug(f"Mecha created for {config_path} successfully")
        for pack in ctx.packs:
            for provider in mc.providers:
                for file_instance, compilation_unit in provider(pack, mc.match):
                    logging.debug(f"Enqueued {compilation_unit.resource_location}")
                    mc.database[file_instance] = compilation_unit
                    mc.database.enqueue(file_instance)

        return ctx
    return None

        
def create_instance(
    config_path: Path, sites: list[str]
) -> Context | None:
    config = load_config(config_path)
    logging.debug(config)
    # Ensure that we aren't loading in all project files
    config.output = None

    config.pipeline = list(filter(lambda p: isinstance(p, str), config.pipeline))

    og_cwd = os.getcwd()
    og_sys_path = sys.path
    og_modules = sys.modules

    sys.path = [*sites, str(config_path.parent), *og_sys_path]

    os.chdir(config_path.parent)


    instance = None

    try:
        instance = create_context(config, config_path)

    except PluginError as plugin_error:
        logging.error(plugin_error.__cause__)
        raise plugin_error.__cause__
    except DiagnosticErrorSummary as summary:
        logging.error("Errors found in the following:")
        for diag in summary.diagnostics.exceptions:
            logging.error("\t" + str(diag.file.source_path))

    except Exception as e:
        logging.error(f"Error occured while running beet: {type(e)} {e}")

    os.chdir(og_cwd)
    sys.path = og_sys_path
    sys.modules = og_modules
    return instance


class MechaLanguageServer(LanguageServer):
    instances: dict[Path, Context]
    _sites: list[str] = []

    def set_sites(self, sites: list[str]):
        self._sites = sites

    def __init__(self, *args):
        super().__init__(*args)
        self.instances = {}

    def setup_workspaces(self):
        config_paths: list[Path] = []

        for w in self.workspace.folders.values():
            ws_path = self.uri_to_path(w.uri)

            for config_type in CONFIG_TYPES:
                for config_path in ws_path.glob("**/" + config_type):
                    config_paths.append(config_path)
                    logging.debug(config_path)

        self.instances = {
            c.parent: create_instance(c, self._sites) for c in config_paths
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

    def get_context(self, document: TextDocument):
        doc_path = Path(document.path)

        parents: list[Path] = []

        for parent_path in self.instances.keys():
            if doc_path.is_relative_to(parent_path):
                parents.append(parent_path)

        parents = sorted(parents, key=lambda p: len(str(p).split(os.path.sep)))
        # logging.debug(parents[-1])
        instance = self.instances[parents[-1]]

        if instance is None:
            instance = create_instance(parents[-1], self._sites)
            self.instances[parents[-1]] = instance

        if instance is not None:
            return instance
        return None
