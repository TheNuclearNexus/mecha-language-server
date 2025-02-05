from copy import copy
import inspect
import logging
from typing import Any, Iterable, cast, get_args, get_origin

from beet import NamespaceFile
from bolt import AstIdentifier, AstTargetIdentifier, Binding, LexicalScope
from lsprotocol import types as lsp
from mecha import AstNode, AstResourceLocation
from tokenstream import SourceLocation

from aegis.reflection import FunctionInfo, TypeInfo, format_function_hints, get_name_of_type, get_type_info

from ..indexing import AegisProjectIndex

from .. import AegisServer
from .validate import get_compilation_data


def get_representation_file(project_index: AegisProjectIndex, node: AstResourceLocation):
    if not (represents := cast(type[NamespaceFile]|str|None, node.__dict__.get("represents"))):
            return None
        
    if isinstance(represents, str):
        return None
        
    return represents



def fetch_compilation_data(ls: AegisServer, params: Any):
    text_doc = ls.workspace.get_document(params.text_document.uri)
    with ls.context(text_doc) as ctx:

        if ctx is None:
            return None

        compiled_doc = get_compilation_data(ctx, text_doc)
        return compiled_doc


def get_node_at_position(root: AstNode, pos: lsp.Position):
    target = SourceLocation(0, pos.line + 1, pos.character + 1)
    nearest_node = root
    for node in root.walk():
        start = node.location
        end = node.end_location

        if not (start.colno <= target.colno and end.colno >= target.colno):
            continue

        if not (start.lineno == target.lineno and end.lineno == target.lineno):
            continue

        if (
            start.pos >= nearest_node.location.pos
            and end.pos <= nearest_node.end_location.pos
        ):
            nearest_node = node

    return nearest_node


def offset_location(location: SourceLocation, offset):
    return SourceLocation(
        location.pos + offset, location.lineno, location.colno + offset
    )



