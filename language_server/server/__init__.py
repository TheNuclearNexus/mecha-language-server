import json
import logging
import sys
from urllib import request
from beet import (
    Context,
    NamespaceFile,
    PluginImportError,
    Project,
    ProjectConfig,
    load_config,
    PluginError,
    locate_config,
)
from beet.library.base import LATEST_MINECRAFT_VERSION


from mecha import Mecha, DiagnosticErrorSummary
from pygls.server import LanguageServer
from pygls.workspace import TextDocument
from lsprotocol import types as lsp
import os

from pathlib import Path
from urllib.parse import unquote, urlparse
from urllib.request import url2pathname

from .shadows import LanguageServerContext, ProjectBuilderShadow



logging.basicConfig(filename="mecha.log", filemode="w", level=logging.DEBUG)

CONFIG_TYPES = ["beet.json", "beet.yaml", "beet.yml"]
GAME_REGISTRIES: dict[str, list[str]] = {}


class MechaLanguageServer(LanguageServer):
    instances: dict[Path, LanguageServerContext] = dict()
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


    def create_context(self, config: ProjectConfig, config_path: Path) -> LanguageServerContext: 
        """Attempt to configure the project's context and run necessary plugins"""
        project = Project(config, None, config_path)

        ctx = ProjectBuilderShadow(project, root=True).initialize(self.show_message)
        logging.debug(f"Mecha created for {config_path} successfully")
        return ctx
            
    def create_instance(
        self, config_path: Path
    ) -> LanguageServerContext | None:
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
        except PluginImportError as plugin_error:
            logging.error(f"Plugin Import Error: {plugin_error}\n{plugin_error.__cause__}")
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

            if config_path := locate_config(ws_path):
                config_paths.append(config_path)            

        for config_path in config_paths:
            try:
                if config := self.create_instance(config_path):
                    self.instances[config_path.parent] = config
            except Exception as exc:
                logging.error(f"Failed to load config at {config_path} due to the following\n{exc}")

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
        logging.debug(parents)
        # logging.debug(parents[-1])
        instance = self.get_instance(parents[-1])

        return instance
