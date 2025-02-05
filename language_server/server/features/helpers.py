from copy import copy
import inspect
import logging
from typing import Any, Iterable, cast, get_args, get_origin

from beet import NamespaceFile
from bolt import AstIdentifier, AstTargetIdentifier, Binding, LexicalScope
from lsprotocol import types as lsp
from mecha import AstNode, AstResourceLocation
from tokenstream import SourceLocation

from ..utils.reflection import FunctionInfo, TypeInfo, format_function_hints, get_name_of_type, get_type_info

from ..indexing import ProjectIndex

from .. import MechaLanguageServer
from .validate import get_compilation_data


def get_representation_file(project_index: ProjectIndex, node: AstResourceLocation):
    if not (represents := cast(type[NamespaceFile]|str|None, node.__dict__.get("represents"))):
            return None
        
    if isinstance(represents, str):
        return None
        
    return represents


def node_location_to_range(node: AstNode | Iterable[SourceLocation]):
    if isinstance(node, AstNode):
        location = node.location
        end_location = node.end_location
    else:
        location, end_location = node

    return lsp.Range(
        start=location_to_position(location), end=location_to_position(end_location)
    )


def node_start_to_range(node: AstNode):
    start = location_to_position(node.location)
    end = lsp.Position(line=start.line, character=start.character + 1)

    return lsp.Range(start=start, end=end)


def location_to_position(location: SourceLocation) -> lsp.Position:
    return lsp.Position(
        line=max(location.lineno - 1, 0),
        character=max(location.colno - 1, 0),
    )


def fetch_compilation_data(ls: MechaLanguageServer, params: Any):
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




def get_doc_string(doc: Any):
    return "\n---\n" + doc if isinstance(doc, str) else ""


def get_variable_description(name: str, value: Any):
    if inspect.isclass(value):
        return f"```python\n(variable) {name}: {get_name_of_type(value)}\n```"

    doc_string = get_doc_string(value.__doc__)
    return f"```python\n(variable) {name}: {get_name_of_type(type(value))}\n```{doc_string}"


def get_class_description(name: str, value: type|TypeInfo):
    if not isinstance(value, TypeInfo):
        value = get_type_info(value)

    doc_string = get_doc_string(value.doc)

    if not (init := value.functions.get("__init__")):
        return f"```python\nclass {name}()\n```{doc_string}"

    init = copy(init)
    init.parameters.pop(0)

    return f"```python\n{format_function_hints(name, init, keyword='class', show_return_type=False)}\n```{doc_string}"

def get_function_description(name: str, function: Any):
    function_info = None
    if isinstance(function, FunctionInfo):
        function_info = function
    else:
        function_info = FunctionInfo.extract(function)

    doc_string = get_doc_string(function_info.doc)

    return f"```py\n{format_function_hints(name, function_info)}\n```{doc_string}"

def get_annotation_description(name: str, type_annotation: Any):
    if get_origin(type_annotation) is type:
        args = get_args(type_annotation)
        description = get_class_description(name, args[0])
    elif isinstance(type_annotation, TypeInfo):
        description = get_class_description(name, type_annotation)
    elif inspect.isfunction(type_annotation) or inspect.isbuiltin(type_annotation) or isinstance(type_annotation, FunctionInfo):
        description = get_function_description(name, type_annotation)
    else:
        description = get_variable_description(name, type_annotation)
        
    return description