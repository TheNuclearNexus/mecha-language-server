from pathlib import Path
from typing import cast

import lsprotocol.types as lsp
from beet import File, NamespaceFile
from bolt import AstAttribute, AstIdentifier, AstImportedItem, AstTargetIdentifier
from mecha import AstResourceLocation

from aegis.ast.features import BaseFeatureProvider
from aegis.ast.metadata import (
    ResourceLocationMetadata,
    VariableMetadata,
    retrieve_metadata,
)
from aegis.indexing.project_index import AegisProjectIndex
from aegis.reflection import get_annotation_description
from aegis_server.server.features.helpers import node_location_to_range
