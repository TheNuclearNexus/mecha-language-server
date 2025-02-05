from functools import partial
import logging
from typing import Callable, TypeVar, cast
from beet.core.utils import required_field
from dataclasses import dataclass, replace
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


def parse_relative_path(self: RelativeResourceLocationParser, stream: TokenStream) -> AstResourceLocation:
    node: AstResourceLocation = self.parser(stream)
    
    if node.namespace is None and node.path.startswith(("./", "../")):
        unresolved = node.path
        namespace, resolved = resolve_using_database(
            relative_path=node.path,
            database=self.database,
            location=node.location,
            end_location=node.end_location,
        )

        node = replace(node, namespace=namespace, path=resolved)
        node.__dict__["unresolved_path"] = unresolved
    else:
        node.__dict__["unresolved_path"] = node.get_canonical_value()
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
