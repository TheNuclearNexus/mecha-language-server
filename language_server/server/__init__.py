from contextlib import ExitStack, contextmanager
from copy import deepcopy
from dataclasses import dataclass, fields
import functools
import importlib
import logging
import sys
from tempfile import TemporaryDirectory
from types import MethodType
from typing import Any, Iterator, List, Type
from beet import (
    Context,
    GenericPlugin,
    PackLoadOptions,
    PluginSpec,
    Project,
    ProjectBuilder,
    Task,
    load_config,
    run_beet,
    PluginError,
    Pipeline,
)
from beet.library.base import LATEST_MINECRAFT_VERSION
from beet.toolchain.template import TemplateManager
from beet.core.utils import import_from_string, normalize_string, change_directory
from beet.toolchain.context import NamespaceFileType

from bolt import Module, Runtime
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


class ContextShadow(Context):
    def _require(self, *args: PluginSpec):
        logging.debug(f"require {args}")
        plugins = []
        for arg in args:
            plugins.append(get_enter_phase(arg))

        super().require(*plugins)

    def require(self, *args: PluginSpec):
        self._require(*args)


def execute_enter_phase(plugin: GenericPlugin, ctx: Context):
    Task(plugin).advance(ctx)

    return


def get_enter_phase(arg: PluginSpec):
    plugin: GenericPlugin = (
        import_from_string(arg, "beet_default", None) if isinstance(arg, str) else arg
    )

    execute = functools.partial(execute_enter_phase, plugin)
    return execute


class ProjectBuilderShadow(ProjectBuilder):

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

            plugins: List[PluginSpec] = [self.bootstrap]
            plugins.extend(
                (
                    item
                    if isinstance(item, str)
                    else ProjectBuilder(
                        Project(
                            resolved_config=item,
                            resolved_cache=ctx.cache,
                            resolved_worker_pool=self.project.worker_pool,
                        )
                    )
                )
                for item in self.config.pipeline
            )

            with change_directory(tmpdir):
                pipeline = stack.enter_context(ctx.activate())
                pipeline.run(plugins)

            yield ctx


def create_instance(
    config_path: Path, sites: list[str]
) -> tuple[Context, Mecha] | None:
    config = load_config(config_path)
    logging.debug(config)
    # Ensure that we aren't loading in all project files
    config.output = None

    if "mecha" not in config.pipeline:
        config.pipeline.insert(0, "mecha")

    config.pipeline = list(filter(lambda p: isinstance(p, str), config.pipeline))

    og_cwd = os.getcwd()
    og_sys_path = sys.path
    og_modules = sys.modules

    sys.path = [*sites, str(config_path.parent), *og_sys_path]

    os.chdir(config_path.parent)

    require = []

    for name in config.require:
        execute = get_enter_phase(name)
        require.append(execute)

    config.require = require

    project = Project(config, None, config_path)

    instance = None

    try:
        with ProjectBuilderShadow(project, root=True).build() as ctx:
            logging.error("Failed to stop pipeline!")

            instance = (ctx, ctx.inject(Mecha))

            for mod in ctx.data[Module]:
                logging.debug(mod)

            logging.debug(f"Mecha created for {config_path} successfully")

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
    instances: dict[Path, tuple[Context, Mecha]]
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

    def get_mecha(self, document: TextDocument):
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
            ctx = instance[0]
            for mod in ctx.data[Module]:
                logging.debug(mod)

            logging.debug(ctx.inject(Runtime).modules.database)

            return instance[1]
        return None
