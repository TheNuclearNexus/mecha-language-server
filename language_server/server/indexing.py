from dataclasses import dataclass, field, fields
import logging
from typing import Any, Generic, TypeVar, cast

from bolt import (
    AstAssignment,
    AstDict,
    AstExpressionBinary,
    AstList,
    AstTarget,
    AstTargetIdentifier,
    AstTuple,
    AstValue,
)
from mecha import AstBlock, AstCommand, AstItemSlot, AstNode, AstParticle, AstRoot, AstSelector, AstSelectorArgument, Reducer, AstResourceLocation, rule, AstItemStack
from mecha.contrib.nested_location import AstNestedLocation

def node_to_types(node: AstNode):
    
    nodes = []
    for n in node.walk():
        if isinstance(n, AstExpressionBinary) and n.operator == "|":
            continue

        nodes.append(n)

    return tuple(nodes)


@dataclass(frozen=True, slots=True)
class AstTypedTarget(AstTarget):
    type_annotation: list[Any] = field(default_factory=list)

@dataclass(frozen=True, slots=True)
class AstTypedTargetIdentifier(AstTargetIdentifier):
    type_annotation: list[Any] = field(default_factory=list)

def expression_to_annotation(expression):
    type_annotation = None
    match (expression):
        case AstValue() as value:
            type_annotation = type(value.value)
        case AstDict() as _dict:
            type_annotation = dict
        case AstList():
            type_annotation = list
        case AstTuple():
            type_annotation = tuple
    return type_annotation

T = TypeVar('T', bound=AstNode)

def index_function_ast(ast: T, function_location: str) -> T:
    resolve_paths(ast, path = "/".join(function_location.split(":")[1:]))
    return MetaDataAttacher()(ast)

def resolve_paths(root: AstNode, path: str = "current"):
    next_path = path
    for child in root:
        if isinstance(child, AstNestedLocation):
            child.__dict__["resolved_path"] = path + "/" + child.path     
            next_path = path + "/" + child.path
        elif isinstance(child, AstResourceLocation):
            next_path = child.path
        
        resolve_paths(child, next_path)

def add_representation(arg_node: AstNode, type: str):
    arg_node.__dict__["represents"] = type

@dataclass
class MetaDataAttacher(Reducer):

    @rule(AstAssignment)
    def assignment(self, node: AstAssignment):
        annotations: list[AstNode | type] = []

        if isinstance(node.target, AstTypedTarget) or isinstance(node.target, AstTypedTargetIdentifier):
            return node

        if node.type_annotation:
            type_annotation = node.type_annotation

            annotations.extend(node_to_types(type_annotation))
        else:
            expression = node.value
            type_annotation = expression_to_annotation(expression)
            if type_annotation:
                annotations.append(type_annotation)

        if len(annotations) > 0:
            node.target.__dict__["type_annotations"] = annotations
        return node



    @rule(AstCommand)
    def command(self, command: AstCommand):
        argument_types = command.identifier.split(':')

        

        for arg_type, arg_node in zip(argument_types[1:], command.arguments):
            
            match arg_node:
                case AstResourceLocation():
                    add_representation(arg_node, arg_type)
    
    @rule(AstBlock)
    def block(self, block: AstBlock):
        add_representation(block.identifier, "block")
        
    @rule(AstItemStack)
    def item_stack(self, item_stack: AstItemStack):
        add_representation(item_stack.identifier, "block")
    
    @rule(AstParticle)
    def particle(self, particle: AstParticle):
        add_representation(particle.name, "particle_type")

    @rule(AstSelectorArgument)
    def selector_argument(self, selector_argument: AstSelectorArgument):
        key = selector_argument.key.value

        if not isinstance(selector_argument.value, AstResourceLocation):
            return
        
        value = selector_argument.value

        match key:
            case "type":
                add_representation(value, "entity_type")