from typing import Any
from beet import Function, TextFileBase
from mecha import AstRoot, Diagnostic, Mecha
from tokenstream import TokenStream 

class MechaLite(Mecha):
    def parse_function(self, function: TextFileBase[Any] | list[str] | str) -> AstRoot:
        if not isinstance(function, TextFileBase):
            function = Function(function)

        stream = TokenStream(
            source=function.text,
            preprocessor=self.preprocessor,
        )

        diagnostics: list[Diagnostic] = []
         
        ast = self.parse_stream(False, {}, AstRoot.parser, stream)

        return ast