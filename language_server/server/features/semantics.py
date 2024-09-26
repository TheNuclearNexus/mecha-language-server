from functools import reduce
import logging
from lsprotocol import types as lsp
from mecha import AstCommand, AstNode, AstResourceLocation
from mecha.contrib.nested_location import AstNestedLocation
from bolt import AstTargetIdentifier
from bolt import (
    AstAssignment,
    AstCall,
    AstFromImport,
    AstFunctionSignature,
    AstIdentifier,
    AstImportedItem,
    AstStatement,
)
from tokenstream import SourceLocation

from language_server.server import MechaLanguageServer
from language_server.server.features.validate import get_compilation_data

TOKEN_TYPE_LIST = [
    "comment",
    "string",
    "keyword",
    "number",
    "regexp",
    "operator",
    "namespace",
    "type",
    "struct",
    "class",
    "interface",
    "enum",
    "typeParameter",
    "function",
    "method",
    "decorator",
    "macro",
    "variable",
    "parameter",
    "property",
    "label",
]

TOKEN_TYPES = {TOKEN_TYPE_LIST[i]: i for i in range(len(TOKEN_TYPE_LIST))}

# token tuple
# 0: line offset
# 1: col offset
# 2: length
# 3: type
# 4: modifier bitflag


def node_to_token(node: AstNode, type: int, modifier: int, prev_node: tuple[AstNode, tuple[int]] | None) -> tuple[int, ...]:
    line_offset = node.location.lineno - 1
    col_offset = node.location.colno - 1
    length = node.end_location.pos - node.location.pos

    if prev_node is not None:
        line_offset -= prev_node[0].location.lineno - 1

        if line_offset == 0:
            col_offset -= prev_node[1][1]

    token = (line_offset, col_offset, length, type, modifier)
    return token


def parse_command(nodes: list[tuple[AstNode, int, int]], node: AstCommand):
    match node.identifier:
        case "import:module":
            modules: list[AstResourceLocation] = node.arguments

            for m in modules:
                nodes.append(
                    (m, TOKEN_TYPES["class" if m.namespace == None else "function"], 0)
                )
        case "import:module:as:alias":
            module: AstResourceLocation = node.arguments[0]
            item: AstImportedItem = node.arguments[1]

            type = TOKEN_TYPES["class" if module.namespace == None else "function"]

            nodes.append((module, type, 0))
            nodes.append((item, type, 0))


def walk(root: AstNode):
    nodes: list[tuple[AstNode, int, int]] = []

    for node in root.walk():
        get_token_type(nodes, node)

    tokens: list[tuple[int]] = []
    for i in range(len(nodes)):
        prev_node = None
        if i > 0:
            prev_node = (nodes[i - 1][0], tokens[i - 1])

        node, type, modifier = nodes[i]
        tokens.append(node_to_token(node, type, modifier, prev_node))

    return list(sum(tokens, ()))


def get_token_type(nodes: list[tuple[AstNode, int, int]], node: AstNode):
    match node:
        case AstFromImport() as from_import:
            handle_from_import(nodes, from_import)

        case AstCommand() as command:
            parse_command(nodes, command)

        case AstAssignment() as assignment:
            handle_assignment(nodes, assignment)

        case AstCall() as call:
            function = call.value
            nodes.append((function, TOKEN_TYPES["function"], 0))

        case AstFunctionSignature() as signature:
            handle_function_sig(nodes, signature)
        case AstNestedLocation() as nested_location:
            nodes.append((nested_location, TOKEN_TYPES["function"], 0))


def handle_function_sig(
    nodes: list[tuple[AstNode, int, int]], signature: AstFunctionSignature
):
    location: SourceLocation = signature.location
    node = AstNode(
        location=location,
        end_location=SourceLocation(
            location.pos + len(signature.name),
            location.lineno,
            location.colno + len(signature.name),
        ),
    )
    nodes.append((node, TOKEN_TYPES["function"], 0))


def handle_assignment(nodes: list[tuple[AstNode, int, int]], assignment: AstAssignment):
    operator = assignment.operator

    nodes.append((assignment.target, TOKEN_TYPES["variable"], 0))

    if assignment.type_annotation != None:
        nodes.append((assignment.type_annotation, TOKEN_TYPES["class"], 0))


def handle_from_import(
    nodes: list[tuple[AstNode, int, int]], from_import: AstFromImport
):
    location: AstResourceLocation = from_import.arguments[0]
    imports: tuple[AstImportedItem] = from_import.arguments[1:]

    nodes.append(
        (
            location,
            TOKEN_TYPES["class" if location.namespace == None else "function"],
            0,
        )
    )

    for i in imports:
        logging.debug(f"{i.location}, {i.end_location}")
        nodes.append((i, TOKEN_TYPES["variable" if i.identifier else "class"], 0))


def semantic_tokens(ls: MechaLanguageServer, params: lsp.SemanticTokensParams):
    text_doc = ls.workspace.get_document(params.text_document.uri)
    ctx = ls.get_context(text_doc)

    if ctx is None:
        data = []
    else:
        compiled_doc = get_compilation_data(ls, ctx, text_doc)
        ast = compiled_doc.ast

        data = walk(ast) if ast else []

    return lsp.SemanticTokens(data=data)
