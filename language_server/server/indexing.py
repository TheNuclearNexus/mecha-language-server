from dataclasses import dataclass, field
import logging
from typing import Any

from bolt import (
    AstAssignment,
    AstDict,
    AstExpression,
    AstExpressionBinary,
    AstIdentifier,
    AstList,
    AstTarget,
    AstTargetIdentifier,
    AstTuple,
    AstValue,
)
from mecha import AstNode, AstRoot, MutatingReducer, Reducer, Visitor, rule


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

@dataclass
class Indexer(Reducer):

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

    