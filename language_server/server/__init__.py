from pygls.server import LanguageServer

from ..mecha import MechaLite

class MechaLanguageServer(LanguageServer):
    mecha: MechaLite
    def __init__(self, *args):
        super().__init__(*args)
        self.mecha = MechaLite()

