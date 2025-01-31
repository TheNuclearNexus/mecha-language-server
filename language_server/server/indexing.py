from ast import Module
from dataclasses import dataclass, field, fields, is_dataclass
from functools import reduce
import inspect
import logging
import types
from typing import Any, Generic, Optional, TypeVar, Union, cast, get_origin
import typing

from beet.core.utils import extra_field
from bolt import (
    AstAssignment,
    AstAttribute,
    AstCall,
    AstDict,
    AstExpressionBinary,
    AstIdentifier,
    AstList,
    AstTarget,
    AstTargetIdentifier,
    AstTuple,
    AstValue,
    CompiledModule,
)
from mecha import (
    AstBlock,
    AstCommand,
    AstItemSlot,
    AstNode,
    AstParticle,
    AstRoot,
    AstSelector,
    AstSelectorArgument,
    Reducer,
    AstResourceLocation,
    rule,
    AstItemStack,
)
from mecha.contrib.nested_location import AstNestedLocation

from .shadows import CompiledDocument

from .utils.reflection import UNKNOWN_TYPE, FunctionInfo, get_type_info


def node_to_types(node: AstNode):

    types = []
    for n in node.walk():
        if isinstance(n, AstExpressionBinary) and n.operator == "|":
            continue

        annotation = expression_to_annotation(n)

        if annotation is not UNKNOWN_TYPE:
            types.append(annotation)

    return reduce(lambda a, b: a | b, types)


@dataclass(frozen=True, slots=True)
class AstTypedTarget(AstTarget):
    type_annotation: list[Any] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class AstTypedTargetIdentifier(AstTargetIdentifier):
    type_annotation: list[Any] = field(default_factory=list)


def expression_to_annotation(expression):
    type_annotation = UNKNOWN_TYPE
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


def was_referenced(references: list[AstNode], identifier: AstNode):
    logging.debug(f"{identifier.location} -> {identifier.end_location}")
    for reference in references:
        logging.debug(f"{reference.location} -> {reference.end_location}")
        if (
            reference.location == identifier.location
            and reference.end_location == identifier.end_location
        ):
            return True


def get_referenced_type(module: CompiledModule, identifier: AstIdentifier):
    var_name = identifier.value
    defined_variables = module.lexical_scope.variables

    if variable := defined_variables.get(var_name):
        for binding in variable.bindings:
            if was_referenced(binding.references, identifier) and (
                type_annotation := get_type_annotation(binding.origin)
            ):
                return type_annotation

    return UNKNOWN_TYPE


T = TypeVar("T", bound=AstNode)


def index_function_ast(
    ast: T, function_location: str, module: CompiledModule | None = None
) -> T:
    resolve_paths(ast, path="/".join(function_location.split(":")[1:]))
    try:
        initial_values = InitialValues()
        bindings = Bindings(module=module)

        return bindings(initial_values(ast))
    except Exception as e:
        logging.error(e)
        raise e


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


def get_type_annotation(node: AstNode) -> Any:
    if node is None:
        return None

    return node.__dict__.get("type_annotations")


def set_type_annotation(node: AstNode, value: Any):
    node.__dict__["type_annotations"] = value


@dataclass
class InitialValues(Reducer):
    @rule(AstAssignment)
    def assignment(self, node: AstAssignment):

        if node.target is None:
            return node

        if node.type_annotation:
            type_annotation = node_to_types(node.type_annotation)
        else:
            expression = node.value
            type_annotation = get_type_annotation(expression)

        if type_annotation is not None:
            set_type_annotation(node.target, type_annotation)
        return node

    @rule(AstValue)
    def value(self, value: AstValue):
        if get_type_annotation(value):
            return value

        set_type_annotation(value, type(value.value))

        return value


@dataclass
class Bindings(Reducer):
    module: Optional[CompiledModule] = extra_field(default=None)

    @rule(AstIdentifier)
    def identifier(self, identifier):
        logging.debug(identifier)
        logging.debug(self.module)
        if get_type_annotation(identifier) or self.module is None:
            return identifier

        set_type_annotation(identifier, get_referenced_type(self.module, identifier))

        return identifier

    @rule(AstAttribute)
    def attribute(self, attribute: AstAttribute):
        if get_type_annotation(attribute):
            return

        base = get_type_annotation(attribute.value)

        if base is UNKNOWN_TYPE or not hasattr(base, attribute.name):
            set_type_annotation(attribute, UNKNOWN_TYPE)
        else:
            set_type_annotation(attribute, getattr(base, attribute.name))

        return attribute

    @rule(AstCall)
    def call(self, call: AstCall):
        if get_type_annotation(call):
            return call

        function = get_type_annotation(call.value)

        if function is UNKNOWN_TYPE:
            set_type_annotation(call, UNKNOWN_TYPE)
            return call

        info = FunctionInfo.extract(function)

        call.__dict__["debug"] = info
        if info.return_annotation is inspect.Parameter.empty:
            set_type_annotation(call, UNKNOWN_TYPE)
            return call

        set_type_annotation(call, info.return_annotation)
        return call

    @rule(AstCommand)
    def command(self, command: AstCommand):
        argument_types = command.identifier.split(":")

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
