from lsprotocol import types as lsp
from beet import Function, ProjectConfig, run_beet
from mecha import Mecha
import pytest


from .. import mecha_server
from ..server import MechaLanguageServer
from ..server.features.validate import parse_function, validate, validate_function
from ..server.features.completion import get_completions


@pytest.fixture
def ls():
    with run_beet(ProjectConfig(require=["bolt"])) as ctx:
        mecha_server.mecha = ctx.inject(Mecha)
    return mecha_server


def test_bolt_python(ls: MechaLanguageServer):
    diagnostics = validate_function(
        ls,
        Function(
            """
foo = 1
if foo == 1:
    print("hi")
"""
        ),
    )
    assert len(diagnostics) == 0


def test_mcfunction(ls: MechaLanguageServer):
    diagnostics = validate_function(
        ls,
        Function(
            """
scoreboard players set @a dummy 1
"""
        ),
    )
    assert len(diagnostics) == 0


COMPLETIONS = [["scoreboard ", lsp.Position(1, 11), 2], ["s", lsp.Position(1, 1), 2]]


def test_completions(ls: MechaLanguageServer):
    for [function, pos, expected] in COMPLETIONS:
        items = get_completions(ls, pos, function)
        assert len(items) == expected
