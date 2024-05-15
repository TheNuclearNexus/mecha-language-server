import logging
from mecha import Mecha
from pygls.server import LanguageServer


logging.basicConfig(filename='mecha.log', filemode='w', level=logging.DEBUG)

class MechaLanguageServer(LanguageServer):
    mecha: Mecha
    def __init__(self, *args):
        super().__init__(*args)
        