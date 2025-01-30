from dataclasses import dataclass, field
import inspect
import logging
from types import NoneType
from typing import Any, Literal, Union, get_args
from beet import Context
from beet.core.utils import required_field
from lsprotocol import types as lsp
from mecha import (
    AstCommand,
    AstItemSlot,
    AstNode,
    AstResourceLocation,
    Reducer,
    Visitor,
    rule,
    Mecha,
)
from mecha.contrib.nested_location import AstNestedLocation
from bolt import (
    AstAttribute,
    AstClassBases,
    AstClassName,
    AstExpression,
    AstExpressionUnary,
    AstFunctionSignatureArgument,
    AstIdentifier,
    AstPrelude,
    AstTarget,
    AstTargetIdentifier,
    AstValue,
)
from bolt import (
    AstAssignment,
    AstCall,
    AstFromImport,
    AstFunctionSignature,
    AstImportedItem,
)
from tokenstream import SourceLocation

from language_server.server import MechaLanguageServer
from ..indexing import get_type_annotation, set_type_annotation
from .helpers import offset_location
from language_server.server.features.validate import get_compilation_data


_TokenModifier = Union[
    Literal["declaration"],
    Literal["definition"],
    Literal["readonly"],
    Literal["static"],
    Literal["deprecated"],
    Literal["abstract"],
    Literal["async"],
    Literal["modification"],
    Literal["documentation"],
    Literal["defaultLibrary"],
]

_TokenType = Union[
    Literal["comment"],
    Literal["string"],
    Literal["keyword"],
    Literal["number"],
    Literal["regexp"],
    Literal["operator"],
    Literal["namespace"],
    Literal["type"],
    Literal["struct"],
    Literal["class"],
    Literal["interface"],
    Literal["enum"],
    Literal["typeParameter"],
    Literal["function"],
    Literal["method"],
    Literal["decorator"],
    Literal["macro"],
    Literal["variable"],
    Literal["parameter"],
    Literal["property"],
    Literal["label"],
]

TOKEN_TYPES: dict[_TokenType, int] = {
    get_args(literal)[0]: i for (i, literal) in enumerate(get_args(_TokenType))
}

TOKEN_MODIFIERS: dict[_TokenModifier, int] = {
    get_args(literal)[0]: pow(2, i)
    for (i, literal) in enumerate(get_args(_TokenModifier))
}

# logging.debug(TOKEN_MODIFIERS)
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
class SemanticTokenCollector(Reducer):
    nodes: list[tuple[AstNode, int, int]] = field(default_factory=list)
    ctx: Context = required_field()

    @rule(AstCommand)
    def command(self, node: AstCommand):
        match node.identifier:
            case "import:module":
                modules: list[AstResourceLocation] = node.arguments  # type: ignore

                for m in modules:
                    self.nodes.append(
                        (
                            m,
                            TOKEN_TYPES["class" if m.namespace == None else "function"],
                            0,
                        )
                    )
            case "import:module:as:alias":
                module: AstResourceLocation = node.arguments[0]  # type: ignore
                item: AstImportedItem = node.arguments[1]  # type: ignore

                type = TOKEN_TYPES["class" if module.namespace == None else "function"]

                self.nodes.append((module, type, 0))
                self.nodes.append((item, type, 0))

    @rule(AstFromImport)
    def from_import(self, from_import: AstFromImport):
        if isinstance(from_import, AstPrelude):
            return

        # logging.debug(from_import)

        location: AstResourceLocation = from_import.arguments[0]  # type: ignore
        imports: tuple[AstImportedItem] = from_import.arguments[1:]  # type: ignore

        self.nodes.append(
            (
                location,
                TOKEN_TYPES["class" if location.namespace == None else "function"],
                0,
            )
        )

        import_offset = len("import")
        self.nodes.append(
            (
                AstNode(
                    offset_location(location.end_location, 1),
                    offset_location(location.end_location, import_offset + 1),
                ),
                TOKEN_TYPES["keyword"],
                0,
            )
        )

        for i in imports:
            # logging.debug(f"{i.name}: {i.location}, {i.end_location}")
            self.nodes.append(
                (i, TOKEN_TYPES["variable" if i.identifier else "class"], 0)
            )

    @rule(AstValue)
    def value(self, value: AstValue):
        if not (annotation := get_type_annotation(value)):
            return

        if annotation is NoneType:
            self.nodes.append(
                (value, TOKEN_TYPES["variable"], TOKEN_MODIFIERS["readonly"])
            )
        elif annotation is bool:
            self.nodes.append((value, TOKEN_TYPES["macro"], 0))

    @rule(AstAttribute)
    def attribute(self, attribute: AstAttribute):

        attribute_location = AstIdentifier(
            location=SourceLocation(
                attribute.end_location.pos - len(attribute.name),
                attribute.end_location.lineno,
                attribute.end_location.colno - len(attribute.name),
            ),
            end_location=attribute.end_location,
            value=attribute.name,
        )

        set_type_annotation(attribute_location, get_type_annotation(attribute))

        self.generic_identifier(attribute_location)

    @rule(AstItemSlot)
    def item_slot(self, item_slot: AstItemSlot):
        self.nodes.append(
            (item_slot, TOKEN_TYPES["variable"], TOKEN_MODIFIERS["readonly"])
        )

    @rule(AstResourceLocation)
    def resource_location(self, resource_location: AstResourceLocation):
        self.nodes.append((resource_location, TOKEN_TYPES["function"], 0))

    @rule(AstClassName)
    def class_name(self, class_name: AstClassName):
        self.nodes.append((class_name, TOKEN_TYPES["class"], 0))

    @rule(AstFunctionSignature)
    def function_signature(self, signature: AstFunctionSignature):
        location: SourceLocation = signature.location
        node = AstNode(
            location=location,
            end_location=offset_location(signature.location, len(signature.name)),
        )
        self.nodes.append((node, TOKEN_TYPES["function"], 0))

        if len(signature.arguments) >= 1:
            first = signature.arguments[0]

            if isinstance(first, AstFunctionSignatureArgument) and first.name == "self":
                self.nodes.append((first, TOKEN_TYPES["macro"], 0))

    @rule(AstFunctionSignatureArgument)
    def function_signature_argument(self, argument: AstFunctionSignatureArgument):
        if argument.type_annotation:
            self.nodes.append((argument.type_annotation, TOKEN_TYPES["class"], 0))

    @rule(AstAssignment)
    def assignment(self, assignment: AstAssignment):
        operator = assignment.operator

        self.generic_identifier(assignment.target)

        if assignment.type_annotation != None:
            self.nodes.append((assignment.type_annotation, TOKEN_TYPES["class"], 0))

    def generic_identifier(self, identifier: Any):
        annotation = get_type_annotation(identifier)

        if annotation is not None and inspect.isfunction(annotation):
            self.nodes.append((identifier, TOKEN_TYPES["function"], 0))
        else:
            kind = TOKEN_TYPES["variable"]
            modifiers = 0
            if hasattr(identifier, "value"):
                value = getattr(identifier, "value")

                if isinstance(value, str):
                    if value.isupper():
                        modifiers += TOKEN_MODIFIERS["readonly"]
                    elif value == "self":
                        kind = TOKEN_TYPES["macro"]

            self.nodes.append(
                (
                    identifier,
                    kind,
                    modifiers,
                )
            )

    @rule(AstIdentifier)
    def identifier(self, identifier: AstIdentifier):
        self.generic_identifier(identifier)

    # @rule(AstExpressionUnary)
    # def expression(self, expression: AstExpressionUnary):
    #     if expression.operator == "not" or expression.operator == "is":
    #         self.nodes.append((expression, TOKEN_TYPES["operator"], TOKEN_MODIFIERS["declaration"]))

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

        # logging.debug(tokens)
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
