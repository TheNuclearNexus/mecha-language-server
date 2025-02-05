from dataclasses import replace
from functools import partial
from typing import Callable, TypeVar, cast

from bolt import AstAttribute, AstIdentifier, AstImportedItem, AstTargetIdentifier
from mecha import AstNode, AstResourceLocation, Rule
from mecha.contrib.nested_location import AstNestedLocation, NestedLocationTransformer
from mecha.contrib.relative_location import (
    RelativeResourceLocationParser,
    resolve_using_database,
)
from tokenstream import TokenStream

from aegis.ast.features import attach_feature_provider

from .feature_providers import ResourceLocationFeatureProvider, VariableFeatureProvider

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

    attach_feature_provider(AstIdentifier, VariableFeatureProvider)
    attach_feature_provider(AstTargetIdentifier, VariableFeatureProvider)
    attach_feature_provider(AstAttribute, VariableFeatureProvider)
    attach_feature_provider(AstImportedItem, VariableFeatureProvider)

    attach_feature_provider(AstResourceLocation, ResourceLocationFeatureProvider)