from functools import partial
import logging
from typing import Callable, TypeVar, cast
from beet.core.utils import required_field
from dataclasses import dataclass
from mecha import AstNode, AstResourceLocation, CompilationDatabase, MutatingReducer, Rule, rule
from mecha.contrib.relative_location import (
    RelativeResourceLocationParser,
    resolve_using_database,
)
from mecha.contrib.nested_location import NestedLocationTransformer, AstNestedLocation
from tokenstream import InvalidSyntax, TokenStream, set_location

T = TypeVar("T", bound=AstNode)

def set_dict(a: T, b: AstNode) -> T:
    a.__dict__["unresolved_path"] = b.__dict__.get("unresolved_path")

    return a

@dataclass(frozen=True)
class AstRelativeLocation(AstResourceLocation):
    """Ast relative location node"""

    def get_value(self) -> str:
        raise set_location(UnresolvedRelativeLocation(self), self)

    def get_canonical_value(self) -> str:
        raise set_location(UnresolvedRelativeLocation(self), self)


@dataclass
class RelativeLocationTransformer(MutatingReducer):
    database: CompilationDatabase = required_field()

    @rule(AstRelativeLocation)
    def relative_location(self, node: AstRelativeLocation):
        namespace, resolved = resolve_using_database(
            node.path, self.database, node.location, node.end_location
        )

        resolved_node = AstResourceLocation(
            is_tag=node.is_tag, namespace=namespace, path=resolved
        )

        return set_dict(set_location(resolved_node, node), node)


class UnresolvedRelativeLocation(InvalidSyntax):
    node: AstRelativeLocation

    def __init__(self, node: AstRelativeLocation):
        super().__init__(node)
        self.node = node

    def __str__(self) -> str:
        tag = "#" * self.node.is_tag
        return f'Unresolved relative location "{tag}{self.node.path}".'


def parse_relative_path(
    self: RelativeResourceLocationParser, stream: TokenStream
) -> AstResourceLocation:
    node: AstResourceLocation = self.parser(stream)

    if node.namespace is None and node.path.startswith(("./", "../")):
        return set_dict(set_location(AstRelativeLocation(path=node.path, is_tag=node.is_tag), node), node)

    return node


def wrap_nested_location(
    original_rule: Callable[
        [NestedLocationTransformer, AstNestedLocation], AstResourceLocation
    ],
    self: NestedLocationTransformer,
    node: AstNestedLocation,
):    
    new_node = original_rule(self, node)
    return set_dict(new_node, node)


def apply_patches():
    RelativeResourceLocationParser.__call__ = parse_relative_path
    nested_location_rule = cast(Rule, NestedLocationTransformer.nested_location)
    nested_location_rule.callback = partial(wrap_nested_location, nested_location_rule.callback)
