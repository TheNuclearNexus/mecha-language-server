import logging
from pygls.server import LanguageServer

from ..mecha import MechaLite

logging.basicConfig(filename='mecha.log', filemode='w', level=logging.DEBUG)

class MechaLanguageServer(LanguageServer):
    mecha: MechaLite
    def __init__(self, *args):
        super().__init__(*args)
        self.mecha = MechaLite()
