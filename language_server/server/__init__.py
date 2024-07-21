import logging
import urllib.parse
from beet import PackLoadOptions, ProjectConfig, load_config, run_beet
from mecha import Mecha
from pygls.server import LanguageServer
from pygls.workspace import TextDocument
import os

from pathlib import Path 
from urllib.parse import unquote, urlparse
from urllib.request import url2pathname

logging.basicConfig(filename="mecha.log", filemode="w", level=logging.DEBUG)

CONFIG_TYPES = ["beet.json", "beet.yaml", "beet.yml"]

def create_mecha(config_path: Path):
    config = load_config(config_path)
    logging.debug(config)
    # Ensure that we aren't loading in all project files
    config.data_pack.load = PackLoadOptions()
    config.resource_pack.load = PackLoadOptions()

    if "mecha" not in config.pipeline:
        config.pipeline.insert(0, "mecha")

    config.pipeline = filter(lambda p: isinstance(p, str), config.pipeline)

    with run_beet(config) as ctx:
        mecha = ctx.inject(Mecha)
        return mecha

 
class MechaLanguageServer(LanguageServer):
    mecha_instances: dict[Path, Mecha]

    def __init__(self, *args):
        super().__init__(*args)
        self.mecha_instances = {}

    def setup_workspaces(self):
        config_paths: list[Path] = []

        for w in self.workspace.folders.values():
            ws_path = self.uri_to_path(w.uri)

            for config_type in CONFIG_TYPES:
                for config_path in ws_path.glob("**/" + config_type):
                    config_paths.append(config_path)

        self.mecha_instances = {c.parent: create_mecha(c) for c in config_paths}
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

        for parent_path in self.mecha_instances.keys():
            if doc_path.is_relative_to(parent_path):
                parents.append(parent_path)

        parents = sorted(parents, key=lambda p: len(str(p).split(os.path.sep)))
        # logging.debug(parents[-1])
        return self.mecha_instances[parents[-1]]         
        
            

