import inspect
import logging
from dataclasses import dataclass, field
from types import NoneType
from typing import Any, Literal, Union, get_args, get_origin

from beet import Context
from beet.core.utils import required_field
from bolt import (
    AstAssignment,
    AstAttribute,
    AstCall,
    AstClassBases,
    AstClassName,
    AstExpression,
    AstExpressionUnary,
    AstFromImport,
    AstFunctionSignature,
    AstFunctionSignatureArgument,
    AstIdentifier,
    AstImportedItem,
    AstPrelude,
    AstTarget,
    AstTargetIdentifier,
    AstValue,
)
from lsprotocol import types as lsp
from mecha import (
    AstCommand,
    AstItemSlot,
    AstMessageText,
    AstNode,
    AstResourceLocation,
    Mecha,
    Reducer,
    Visitor,
    rule,
)
from mecha.contrib.nested_location import AstNestedLocation
from tokenstream import SourceLocation, set_location

from aegis.reflection import FunctionInfo, TypeInfo
from aegis.semantics import TokenType, TokenModifier

from ...server import AegisServer
from ..features.validate import get_compilation_data

from ..indexing import get_type_annotation, set_type_annotation
from .helpers import offset_location

TOKEN_TYPES: dict[TokenType, int] = {
    get_args(literal)[0]: i for (i, literal) in enumerate(get_args(TokenType))
}

TOKEN_MODIFIERS: dict[TokenModifier, int] = {
    get_args(literal)[0]: pow(2, i)
    for (i, literal) in enumerate(get_args(TokenModifier))
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

        end_location = node.end_location

        prototypes = self.ctx.inject(Mecha).spec.prototypes

        if len(node.arguments) > 0:
            if node.identifier in prototypes:
                name_length = len(prototypes[node.identifier].signature[0])

                end_location = SourceLocation(
                    lineno=node.location.lineno,
                    pos=node.location.pos + name_length,
                    colno=node.location.colno + name_length,
                )
            # if node.location.lineno == node.arguments[0].location.lineno:
            #     command_name_offset = (
            #         node.arguments[0].location.pos - node.location.pos - 1
            #     )
            #     end_location = SourceLocation(
            #         lineno=node.location.lineno,
            #         pos=node.location.pos + command_name_offset,
            #         colno=node.location.colno + command_name_offset,
            #     )
            else:
                return

        temp_node = AstNode(location=node.location, end_location=end_location)

        self.nodes.append(
            (
                temp_node,
                (
                    TOKEN_TYPES["keyword"]
                    if "subcommand" not in node.identifier
                    or node.identifier == "execute:subcommand"
                    else TOKEN_TYPES["macro"]
                ),
                0,
            )
        )

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

    @rule(AstImportedItem)
    def imported_item(self, imported_item: AstImportedItem):
        self.generic_identifier(imported_item.name, imported_item)

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

        self.generic_identifier(attribute.name, attribute_location)

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

    # @rule(AstAssignment)
    # def assignment(self, assignment: AstAssignment):
    #     self.generic_identifier(assignment.target)

    #     if assignment.type_annotation != None:
    #         self.nodes.append((assignment.type_annotation, TOKEN_TYPES["class"], 0))

    def generic_identifier(self, variable_name: str, identifier: Any):
        annotation = get_type_annotation(identifier)

        if annotation is not None and (
            inspect.isfunction(annotation) or inspect.isbuiltin(annotation) or isinstance(annotation, FunctionInfo)
        ):
            self.nodes.append((identifier, TOKEN_TYPES["function"], 0))
        elif annotation is not None and (get_origin(annotation) is type or isinstance(annotation, TypeInfo)):
            self.nodes.append((identifier, TOKEN_TYPES["class"], 0))
        else:
            kind = TOKEN_TYPES["variable"]
            modifiers = 0
            
            if variable_name.isupper():
                modifiers += TOKEN_MODIFIERS["readonly"]
            elif variable_name == "self":
                kind = TOKEN_TYPES["macro"]

            self.nodes.append(
                (
                    identifier,
                    kind,
                    modifiers,
                )
            )

    @rule(AstIdentifier, AstTargetIdentifier)
    def identifier(self, identifier: AstIdentifier | AstTargetIdentifier):
        self.generic_identifier(identifier.value, identifier)

    # @rule(AstExpressionUnary)
    # def expression(self, expression: AstExpressionUnary):
    #     if expression.operator == "not" or expression.operator == "is":
    #         self.nodes.append((expression, TOKEN_TYPES["operator"], TOKEN_MODIFIERS["declaration"]))

    def walk(self, root: AstNode):
        self.nodes = []
        self.__call__(root)

        tokens: list[tuple[int, ...]] = []

        self.nodes = sorted(self.nodes, key=lambda n: n[0].location.pos)
        for i in range(len(self.nodes)):
            prev_node = None
            if i > 0:
                prev_node = self.nodes[i - 1][0]

            node, type, modifier = self.nodes[i]
            tokens.append(node_to_token(node, type, modifier, prev_node))

        # logging.debug(tokens)
        return list(sum(tokens, ()))


def semantic_tokens(ls: AegisServer, params: lsp.SemanticTokensParams):
    text_doc = ls.workspace.get_document(params.text_document.uri)
    with ls.context(text_doc) as ctx:
        if ctx is None:
            data = []
        else:
            if compiled_doc := get_compilation_data(ctx, text_doc):
                ast = compiled_doc.ast

                data = SemanticTokenCollector(ctx=ctx).walk(ast) if ast else []
            else:
                data = []

    return lsp.SemanticTokens(data=data)
