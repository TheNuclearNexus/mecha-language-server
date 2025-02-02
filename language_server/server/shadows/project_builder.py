import logging
import os
from contextlib import ExitStack
from copy import deepcopy
from typing import Any

from beet import (
    LATEST_MINECRAFT_VERSION,
    Context,
    PluginSpec,
    ProjectBuilder,
    TemplateManager,
)
from beet.contrib.load import load
from beet.core.utils import change_directory, normalize_string
from mecha import AstResourceLocation, Dispatcher, Mecha, MutatingReducer, Reducer

from pygls.server import LanguageServer
from tokenstream import TokenStream

from ..patches import apply_patches

from .pipeline import PipelineShadow

from ..indexing import ProjectIndex
from .context import LanguageServerContext, get_excluded_plugins

__all__ = ["ProjectBuilderShadow"]


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
                _pipeline=PipelineShadow,
                ls=ls,
                project_config=self.config,
                project_id=self.config.id or normalize_string(name),
                project_name=name,
                project_description=self.config.description,
                project_author=self.config.author,
                project_version=self.config.version,
                project_root=self.root,
                minecraft_version=(
                    self.config.minecraft
                    if len(self.config.minecraft) > 0
                    else LATEST_MINECRAFT_VERSION
                ),
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

            pipelined_plugin: list[PluginSpec] = [self.bootstrap]

            excluded_plugins = get_excluded_plugins(ctx)
            for item in self.config.pipeline:
                if (
                    item == "mecha"
                    or not isinstance(item, str)
                    or item in excluded_plugins
                ):
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

            project_index = ProjectIndex.get(ctx)

            mc = ctx.inject(Mecha)

            configure_mecha(mc)

            for pack in ctx.packs:

                # Build a map of file path to resource location
                for location, file in pack.all():
                    try:
                        path = os.path.normpath(file.ensure_source_path())
                        path = os.path.normcase(path)
                        ctx.path_to_resource[str(path)] = (location, file)
                        project_index[type(file)].add_definition(location, path)
                    except:
                        continue

            return ctx


def configure_mecha(mc: Mecha):
    # mc.steps = mc.steps[: mc.steps.index(mc.lint) + 1]

    apply_patches()
