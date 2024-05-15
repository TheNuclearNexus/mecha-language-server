import argparse
from beet import ProjectConfig, run_beet
from bolt import Runtime
from lsprotocol import types as lsp
from mecha import Mecha

from .server import MechaLanguageServer
from .server.features import validate, validate_function, completion
from . import mecha_server



@mecha_server.feature(lsp.TEXT_DOCUMENT_DID_CHANGE)
def did_change(ls: MechaLanguageServer, params: lsp.TextDocumentDidChangeNotification):
    validate(ls, params)


@mecha_server.feature(lsp.TEXT_DOCUMENT_DID_OPEN)
def did_open(ls: MechaLanguageServer, params: lsp.DidOpenTextDocumentParams):
    validate(ls, params)


@mecha_server.feature(
    lsp.TEXT_DOCUMENT_COMPLETION, lsp.CompletionOptions(trigger_characters=[" "])
)
def get_completion(ls: MechaLanguageServer, params: lsp.CompletionParams):
    return completion(ls, params)


def add_arguments(parser):
    parser.description = "simple json server example"

    parser.add_argument("--tcp", action="store_true", help="Use TCP server")
    parser.add_argument("--ws", action="store_true", help="Use WebSocket server")
    parser.add_argument("--host", default="127.0.0.1", help="Bind to this address")
    parser.add_argument("--port", type=int, default=2087, help="Bind to this port")
    parser.add_argument("--plugins", type=str, nargs="*", default=[], help="Plugins to load")


def main():
    print("Starting Mecha LS")
    parser = argparse.ArgumentParser()
    add_arguments(parser)
    args = parser.parse_args()
    print(args)
    with run_beet(ProjectConfig(pipeline=["mecha"], require=args.plugins)) as ctx:
        mecha_server.mecha = ctx.inject(Mecha)

        if args.tcp:
            mecha_server.start_tcp(args.host, args.port)
        elif args.ws:
            mecha_server.start_ws(args.host, args.port)
        else:
            mecha_server.start_io()


if __name__ == "__main__":
    main()
