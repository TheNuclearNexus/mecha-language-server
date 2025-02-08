from dataclasses import dataclass, field

from beet import Context
from bolt import (
    AstAttribute,
    AstClassName,
    AstFormatString,
    AstFunctionSignature,
    AstFunctionSignatureArgument,
    AstIdentifier,
    AstImportedItem,
    AstTargetAttribute,
    AstTargetIdentifier,
    AstValue,
)
from mecha import AstNode, AstResourceLocation, AstItemSlot

from .provider import *
from .resource_location import *
from .variable import *
from .generic import *

def get_default_providers() -> dict[type[AstNode], type[BaseFeatureProvider]]:
    return {
        # Bolt Specific
        AstIdentifier: VariableFeatureProvider,
        AstAttribute: VariableFeatureProvider,
        AstTargetAttribute: VariableFeatureProvider,
        AstTargetIdentifier: VariableFeatureProvider,
        AstImportedItem: VariableFeatureProvider,
        AstClassName: ClassNameProvider,
        AstFunctionSignature: FunctionSignatureProvider,
        AstFunctionSignatureArgument: FunctionSignatureArgProvider,
        AstValue: ValueProvider,
        AstFormatString: FormatStringProvider,
        # Mecha Specific
        AstResourceLocation: ResourceLocationFeatureProvider,
        AstItemSlot: ItemSlotProvider,
    }


@dataclass
class AegisFeatureProviders:
    ctx: Context
    _providers: dict[type[AstNode], type[BaseFeatureProvider]] = field(
        init=False, default_factory=get_default_providers
    )

    def attach(self, node_type: type[AstNode], provider: type[BaseFeatureProvider]):
        self._providers[node_type] = provider

    def retrieve(
        self,
        node_type: type[AstNode] | AstNode,
    ) -> type[BaseFeatureProvider]:
        if not isinstance(node_type, type):
            node_type = type(node_type)

        return self._providers.get(node_type, BaseFeatureProvider)
