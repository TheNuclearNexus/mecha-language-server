import argparse
import logging

from lsprotocol import types as lsp

import language_server
import language_server.server.features.hover
from language_server.server.features.semantics import (
    TOKEN_MODIFIERS,
    TOKEN_TYPES,
    semantic_tokens,
)
from .server.indexing import ProjectIndex

from . import mecha_server
from .server import MechaLanguageServer
from .server.features.completion import completion
from .server.features.definition import get_definition
from .server.features.diagnostics import publish_diagnostics
from .server.features.hover import get_hover
from .server.features.references import get_references
from .server.features.rename import rename_variable


@mecha_server.feature(lsp.TEXT_DOCUMENT_DID_CHANGE)
def did_change(ls: MechaLanguageServer, params: lsp.DidChangeTextDocumentParams):
    publish_diagnostics(ls, params)


@mecha_server.feature(lsp.TEXT_DOCUMENT_DID_OPEN)
def did_open(ls: MechaLanguageServer, params: lsp.DidOpenTextDocumentParams):
    publish_diagnostics(ls, params)


@mecha_server.feature(
    lsp.TEXT_DOCUMENT_COMPLETION, lsp.CompletionOptions(trigger_characters=[" ", "/", "."])
)
def get_completion(ls: MechaLanguageServer, params: lsp.CompletionParams):
    return completion(ls, params)


@mecha_server.feature(lsp.INITIALIZED)
def initialized(ls: MechaLanguageServer, params: lsp.InitializedParams):
    ls.setup_workspaces()


@mecha_server.feature(lsp.WORKSPACE_DID_CHANGE_WORKSPACE_FOLDERS)
def folders_changed(
    ls: MechaLanguageServer, params: lsp.DidChangeWorkspaceFoldersParams
):
    ls.setup_workspaces()


@mecha_server.feature(
    lsp.TEXT_DOCUMENT_SEMANTIC_TOKENS_FULL,
    lsp.SemanticTokensLegend(
        token_types=list(TOKEN_TYPES.keys()),
        token_modifiers=list(TOKEN_MODIFIERS.keys()),
    ),
)
def semantic_tokens_full(ls: MechaLanguageServer, params: lsp.SemanticTokensParams):
    return semantic_tokens(ls, params)


@mecha_server.feature(lsp.TEXT_DOCUMENT_DEFINITION)
def definition(ls: MechaLanguageServer, params: lsp.DefinitionParams):
    return get_definition(ls, params)


@mecha_server.feature(lsp.TEXT_DOCUMENT_REFERENCES)
def references(ls: MechaLanguageServer, params: lsp.ReferenceParams):
    return get_references(ls, params)


@mecha_server.feature(lsp.TEXT_DOCUMENT_HOVER)
def hover(ls: MechaLanguageServer, params: lsp.HoverParams):
    return get_hover(ls, params)


@mecha_server.feature(lsp.TEXT_DOCUMENT_RENAME)
def rename(ls: MechaLanguageServer, params: lsp.RenameParams):
    return rename_variable(ls, params)

@mecha_server.command('mecha.server.dumpIndices')
def dump(ls: MechaLanguageServer, *args):
    ls.show_message_log(ProjectIndex.dump())

@mecha_server.command('mecha.server.toggleASTDebug')
def toggle_ast_debug(ls: MechaLanguageServer, *args):
    language_server.server.features.hover.DEBUG_AST = not language_server.server.features.hover.DEBUG_AST

def add_arguments(parser: argparse.ArgumentParser):
    parser.description = "simple json server example"

    parser.add_argument("--tcp", action="store_true", help="Use TCP server")
    parser.add_argument("--ws", action="store_true", help="Use WebSocket server")
    parser.add_argument("--host", default="127.0.0.1", help="Bind to this address")
    parser.add_argument("--port", type=int, default=2087, help="Bind to this port")
    parser.add_argument(
        "--site",
        type=str,
        default=[],
        nargs="*",
        help="Sites to look for python packages",
    )
    parser.add_argument(
        "--debug_ast",
        type=bool,
        default=False,
        help="Show the AST node for the hovered token",
    )


def main():
    print("Starting Mecha LS")
    parser = argparse.ArgumentParser()
    add_arguments(parser)
    args = parser.parse_args()

    language_server.server.features.hover.DEBUG_AST = args.debug_ast

    mecha_server.set_sites(args.site)

    if args.tcp:
        mecha_server.start_tcp(args.host, args.port)
    elif args.ws:
        mecha_server.start_ws(args.host, args.port)
    else:
        mecha_server.start_io()

    mecha_server._kill()


if __name__ == "__main__":
    main()
