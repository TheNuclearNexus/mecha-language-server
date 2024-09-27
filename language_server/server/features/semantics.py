from dataclasses import dataclass, field
import logging
from beet import Context
from beet.core.utils import required_field
from lsprotocol import types as lsp
from mecha import AstCommand, AstItemSlot, AstNode, AstResourceLocation, Visitor, rule, Mecha
from mecha.contrib.nested_location import AstNestedLocation
from bolt import AstAttribute, AstPrelude
from bolt import (
    AstAssignment,
    AstCall,
    AstFromImport,
    AstFunctionSignature,
    AstImportedItem,
)
from tokenstream import SourceLocation

from language_server.server import MechaLanguageServer
from .helpers import offset_location
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

TOKEN_MODIFIER_LIST = [
    "declaration",
	"definition",
	"readonly",
	"static",
	"deprecated",
	"abstract",
	"async",
	"modification",
	"documentation",
	"defaultLibrary",
]

TOKEN_TYPES = {TOKEN_TYPE_LIST[i]: i for i in range(len(TOKEN_TYPE_LIST))}
TOKEN_MODIFIERS = {TOKEN_MODIFIER_LIST[i]: i for i in range(len(TOKEN_MODIFIER_LIST))}
# token tuple
# 0: line offset
# 1: col offset
# 2: length
# 3: type
# 4: modifier bitflag


def node_to_token(
    node: AstNode,
    type: int,
    modifier: int,
    prev_node: AstNode | None, 
) -> tuple[int, ...]:
    line_offset = node.location.lineno - 1
    col_offset = node.location.colno - 1
    length = node.end_location.pos - node.location.pos

    if prev_node is not None:
        line_offset -= prev_node.location.lineno - 1

        if line_offset == 0:
            col_offset -= prev_node.location.colno - 1

    token = (line_offset, col_offset, length, type, modifier)
    return token

@dataclass
class SemanticTokenCollector(Visitor):
    nodes: list[tuple[AstNode, int, int]] = field(default_factory=list)
    ctx: Context = required_field()
    

    @rule(AstCommand)
    def command(self, node: AstCommand):
        match node.identifier:
            case "import:module":
                modules: list[AstResourceLocation] = node.arguments #type: ignore

                for m in modules:
                    self.nodes.append(
                        (m, TOKEN_TYPES["class" if m.namespace == None else "function"], 0)
                    )
            case "import:module:as:alias":
                module: AstResourceLocation = node.arguments[0] #type: ignore
                item: AstImportedItem = node.arguments[1] #type: ignore

                type = TOKEN_TYPES["class" if module.namespace == None else "function"]

                self.nodes.append((module, type, 0))
                self.nodes.append((item, type, 0))


    @rule(AstFromImport)
    def from_import(self, from_import: AstFromImport):
        if isinstance(from_import, AstPrelude):
            return
        
        logging.debug(from_import)

        location: AstResourceLocation = from_import.arguments[0] #type: ignore
        imports: tuple[AstImportedItem] = from_import.arguments[1:] #type: ignore

        self.nodes.append(
            (
                location,
                TOKEN_TYPES["class" if location.namespace == None else "function"],
                0,
            )
        )

        import_offset = len("import")
        self.nodes.append((
            AstNode(
                offset_location(location.end_location, 1),
                offset_location(location.end_location, import_offset + 1)
            ),
            TOKEN_TYPES["keyword"],
            0
        ))

        for i in imports:
            logging.debug(f"{i.name}: {i.location}, {i.end_location}")
            self.nodes.append((i, TOKEN_TYPES["variable" if i.identifier else "class"], 0))


    @rule(AstCall)
    def call(self, call: AstCall):
        if isinstance(call.value, AstAttribute):
            attribute = call.value
            offset = len(attribute.name)

            call_start = SourceLocation(
                attribute.end_location.pos - offset,
                attribute.end_location.lineno,
                attribute.end_location.colno - offset,
            )

            function = AstNode(
                call_start,
                attribute.end_location,
            )

            base = AstNode(
                attribute.location,
                call_start
            )

            self.nodes.append((base, TOKEN_TYPES["variable"], 0))
            self.nodes.append((function, TOKEN_TYPES["function"], 0))
        else:
            self.nodes.append((call.value, TOKEN_TYPES["function"], 0))


    @rule(AstItemSlot)
    def item_slot(self, item_slot: AstItemSlot):
        self.nodes.append((item_slot, TOKEN_TYPES["variable"], TOKEN_MODIFIERS["readonly"]))

    @rule(AstResourceLocation)
    def resource_location(self, resource_location: AstResourceLocation):
        self.nodes.append((resource_location, TOKEN_TYPES["function"], 0))

    @rule(AstFunctionSignature)
    def function_signature(
        self, signature: AstFunctionSignature
    ):
        location: SourceLocation = signature.location
        node = AstNode(
            location=location,
            end_location=offset_location(signature.location, len(signature.name))
        )
        self.nodes.append((node, TOKEN_TYPES["function"], 0))

    @rule(AstAssignment)
    def assignment(self, assignment: AstAssignment):
        operator = assignment.operator

        self.nodes.append((assignment.target, TOKEN_TYPES["variable"], 0))

        if assignment.type_annotation != None:
            self.nodes.append((assignment.type_annotation, TOKEN_TYPES["class"], 0))


    def walk(self, root: AstNode):
        self.nodes = []
        self.__call__(root)

        tokens: list[tuple[int, ...]] = []

        for i in range(len(self.nodes)):
            prev_node = None
            if i > 0:
                prev_node = self.nodes[i - 1][0]

            node, type, modifier = self.nodes[i]
            tokens.append(node_to_token(node, type, modifier, prev_node))

        return list(sum(tokens, ()))


def semantic_tokens(ls: MechaLanguageServer, params: lsp.SemanticTokensParams):
    text_doc = ls.workspace.get_document(params.text_document.uri)
    ctx = ls.get_context(text_doc)

    if ctx is None:
        data = []
    else:
        compiled_doc = get_compilation_data(ls, ctx, text_doc)
        ast = compiled_doc.ast

        data = SemanticTokenCollector(ctx=ctx).walk(ast) if ast else []

    return lsp.SemanticTokens(data=data)
