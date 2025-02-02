import builtins
from copy import deepcopy
import inspect
import logging
from dataclasses import dataclass
from functools import reduce
from pathlib import Path
import re
from threading import Lock
import traceback
from typing import (
    Any,
    Callable,
    ClassVar,
    Optional,
    TypeVar,
    get_args,
    get_origin,
)

from beet import (
    Advancement,
    Context,
    File,
    Function,
    LootTable,
    NamespaceFile,
    Predicate,
    TextFileBase,
)
from beet.core.utils import required_field, extra_field
from bolt import (
    AstAssignment,
    AstAttribute,
    AstCall,
    AstDict,
    AstExpressionBinary,
    AstIdentifier,
    AstList,
    AstTuple,
    AstValue,
    CompiledModule,
    Module,
    Runtime,
)
from mecha import (
    AbstractNode,
    AstBlock,
    AstChildren,
    AstCommand,
    AstItemStack,
    AstJson,
    AstJsonObject,
    AstNode,
    AstParticle,
    AstResourceLocation,
    AstRoot,
    AstSelectorArgument,
    CompilationError,
    Dispatcher,
    Mecha,
    MutatingReducer,
    Reducer,
    rule,
)
from mecha.contrib.nested_location import (
    AstNestedLocation,
    NestedLocationResolver,
    NestedLocationTransformer,
)
from tokenstream import SourceLocation

from .shadows.context import LanguageServerContext
from .utils.reflection import UNKNOWN_TYPE, FunctionInfo

FilePointer = tuple[SourceLocation, SourceLocation]

Node = TypeVar("Node", bound=AstNode)


@dataclass
class ResourceIndice:
    definitions: dict[str, set[FilePointer]] = extra_field(default_factory=dict)
    references: dict[str, set[FilePointer]] = extra_field(default_factory=dict)

    def _dump(self) -> str:
        dump = ""

        dump += "definitions:\n"
        for path, pointers in self.definitions.items():
            for pointer in pointers:
                dump += f"\t- {path} {pointer[0].lineno}:{pointer[0].colno} -> {pointer[1].lineno}:{pointer[1].colno}\n"
        dump += "references:\n"
        for path, pointers in self.references.items():
            for pointer in pointers:
                dump += f"\t- {path} {pointer[0].lineno}:{pointer[0].colno} -> {pointer[1].lineno}:{pointer[1].colno}\n"

        return dump


def valid_resource_location(path: str):
    return bool(re.match(r"^[a-z0-9_\.]+:[a-z0-9_\.]+(\/?[a-z0-9_\.]+)*$", path))


@dataclass
class ResourceIndex:
    _files: dict[str, ResourceIndice] = extra_field(default_factory=dict)
    _lock: Lock = extra_field(default_factory=Lock)

    def remove_associated(self, path: str | File):
        self._lock.acquire()

        if isinstance(path, File):
            path = str(Path(path.ensure_source_path()).absolute())

        for file, indice in list(self._files.items()):
            if path in indice.definitions:
                del indice.definitions[path]
            if path in indice.references:
                del indice.references[path]

            if len(indice.definitions) == 0:
                del self._files[file]

        self._lock.release()

    def add_definition(
        self,
        resource_path: str,
        source_path: str,
        source_location: FilePointer = (
            SourceLocation(0, 0, 0),
            SourceLocation(0, 0, 0),
        ),
    ):
        if not valid_resource_location(resource_path):
            raise Exception(f"Invalid resource location {resource_path}")

        self._lock.acquire()

        indice = self._files.setdefault(resource_path, ResourceIndice())
        locations = indice.definitions.setdefault(source_path, set())
        locations.add(source_location)

        self._lock.release()

    def get_definitions(
        self, resource_path: str
    ) -> list[tuple[str, SourceLocation, SourceLocation]]:
        if not (file := self._files.get(resource_path)):
            return []

        definitions = []
        for path, locations in file.definitions.items():
            for location in locations:
                definitions.append((path, *location))

        return definitions
    
    def get_references(
        self, resource_path: str
    ) -> list[tuple[str, SourceLocation, SourceLocation]]:
        if not (file := self._files.get(resource_path)):
            return []

        references = []
        for path, locations in file.references.items():
            for location in locations:
                references.append((path, *location))

        return references

    def add_reference(
        self,
        resource_path: str,
        source_path: str,
        source_location: FilePointer = (
            SourceLocation(0, 0, 0),
            SourceLocation(0, 0, 0),
        ),
    ):
        if not valid_resource_location(resource_path):
            raise Exception(f"Invalid resource location {resource_path}")

        self._lock.acquire()

        indice = self._files.setdefault(resource_path, ResourceIndice())
        locations = indice.references.setdefault(source_path, set())
        locations.add(source_location)

        self._lock.release()

    def __iter__(self):
        items = self._files.keys()

        for item in items:
            yield item

    def _dump(self) -> str:
        dump = ""

        for file, indice in self._files.items():
            dump += f"\n- '{file}':\n"
            dump += "\t" + "\n\t".join(indice._dump().splitlines())

        return dump


class ProjectIndex:
    _projects: ClassVar[dict[str, "ProjectIndex"]] = dict()
    _resources: dict[type[NamespaceFile], ResourceIndex] = dict()
    _ctx: Context

    resource_name_to_type: dict[str, type[NamespaceFile]] = dict()

    def __init__(self, ctx: Context):
        self._ctx = ctx

        self.resource_name_to_type = {t.snake_name: t for t in ctx.get_file_types()}

    def __getitem__(self, key: type[NamespaceFile]):
        return self._resources.setdefault(key, ResourceIndex())

    @staticmethod
    def get(ctx: "LanguageServerContext") -> "ProjectIndex":
        return ProjectIndex._projects.setdefault(ctx.project_uuid, ProjectIndex(ctx))

    def remove_associated(self, path: str):
        for resource in self._resources.values():
            resource.remove_associated(path)

    def _dump(self) -> str:
        dump = ""
        for resource, index in self._resources.items():
            dump += f"\nResource {resource.__name__}:"
            dump += "\t" + "\n\t".join(index._dump().splitlines())

        return dump

    @staticmethod
    def dump() -> str:
        dump = ""
        for uuid, index in ProjectIndex._projects.items():
            dump += f"\nProject {uuid}:"
            dump += "\t" + "\n\t".join(index._dump().splitlines())
        return dump.replace("\t", " " * 4)


def node_to_types(node: AstNode):

    types = []
    for n in node.walk():
        if isinstance(n, AstExpressionBinary) and n.operator == "|":
            continue

        annotation = expression_to_annotation(n)

        if annotation is not UNKNOWN_TYPE:
            types.append(annotation)

    return reduce(lambda a, b: a | b, types)


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
    for reference in references:
        if (
            reference.location == identifier.location
            and reference.end_location == identifier.end_location
        ):
            return True


def is_builtin(identifier: AstIdentifier):
    if identifier.value.startswith("_"):
        return None

    return (
        getattr(builtins, identifier.value)
        if hasattr(builtins, identifier.value)
        else None
    )


def annotate_types(annotation):
    if isinstance(annotation, type):
        return type[annotation]
    elif inspect.isfunction(annotation) or inspect.isbuiltin(annotation):
        return annotation
    else:
        return type(annotation)


def get_referenced_type(
    runtime: Runtime, module: CompiledModule, identifier: AstIdentifier
):
    var_name = identifier.value
    defined_variables = module.lexical_scope.variables

    if variable := defined_variables.get(var_name):
        for binding in variable.bindings:
            if was_referenced(binding.references, identifier) and (
                annotation := get_type_annotation(binding.origin)
            ):
                return annotation
    elif identifier.value in module.globals:
        return annotate_types(runtime.globals[identifier.value])

    elif annotation := is_builtin(identifier):
        return annotate_types(annotation)

    return UNKNOWN_TYPE


def add_representation(arg_node: AstNode, type: Any):
    arg_node.__dict__["represents"] = type


def get_type_annotation(node: AstNode) -> Any:
    if node is None:
        return None

    return node.__dict__.get("type_annotations")


def set_type_annotation(node: AstNode, value: Any):
    node.__dict__["type_annotations"] = value


@dataclass
class InitialStep(Reducer):
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

    @rule(AstResourceLocation)
    def resource_location(self, node: AstResourceLocation):
        
        if isinstance(node, AstNestedLocation):
            node.__dict__["unresolved_path"] = f"~/" + node.path
        else:
            node.__dict__.setdefault("unresolved_path", node.get_canonical_value())


@dataclass
class BindingStep(Reducer):
    index: ProjectIndex = required_field()
    source_path: str = required_field()
    runtime: Runtime = required_field()
    mecha: Mecha = required_field()

    parser_to_file_type: dict[str, type[NamespaceFile]] = required_field()

    module: Optional[CompiledModule] = required_field()

    defined_files = []

    @rule(AstIdentifier)
    def identifier(self, identifier):
        if (
            get_type_annotation(identifier)
            or self.module is None
            or self.runtime is None
        ):
            return identifier

        set_type_annotation(
            identifier, get_referenced_type(self.runtime, self.module, identifier)
        )

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

        callable = get_type_annotation(call.value)

        if callable is UNKNOWN_TYPE:
            set_type_annotation(call, UNKNOWN_TYPE)
            return call

        # If the callable is a type of a type
        # then its type annotation should be the
        # method signature of its constructor
        if get_origin(callable) is type:
            callable = get_args(callable)[0]
            info = FunctionInfo.extract(callable.__call__)
            info.return_annotation = callable
        else:
            info = FunctionInfo.extract(callable)

        if info.return_annotation is inspect.Parameter.empty:
            set_type_annotation(call, UNKNOWN_TYPE)
            return call

        set_type_annotation(call, info.return_annotation)
        return call

    @rule(AstCommand)
    def command(self, command: AstCommand):
        if not (prototype := self.mecha.spec.prototypes.get(command.identifier)):
            return

        for i, argument in enumerate(command.arguments):

            match argument:
                case AstResourceLocation():

                    # Attempt to get the parser for the argument
                    argument_tree = prototype.get_argument(i)
                    command_tree_node = self.mecha.spec.tree.get(argument_tree.scope)
                    if not (command_tree_node and command_tree_node.parser):
                        continue

                    # If the parser is registered or the parent argument's name is registered
                    # use that file type for its representation
                    file_type = self.parser_to_file_type.get(
                        command_tree_node.parser
                    ) or self.index.resource_name_to_type.get(argument_tree.scope[-2])

                    if file_type is None:
                        continue


                    # Ensure that unfinished paths are not added to the project index
                    resolved_path = argument.get_canonical_value()

                    # If the argument is a tag then we need to remove the leading
                    # "#" and try to change the file type to the tag equivalent
                    # ex. Function -> FunctionTag
                    if argument.is_tag:
                        resolved_path = resolved_path[1:]
                        if not (
                            file_type := self.index.resource_name_to_type.get(
                                file_type.snake_name + "_tag"
                            )
                        ):
                            continue

                    add_representation(argument, file_type)

                    if not valid_resource_location(resolved_path):
                        continue

                    # Check the command tree for the pattern:
                    # resource_location, defintion
                    # which is used by the nested resource plugin to define a new resource
                    if i + 1 < len(command.arguments) and isinstance(
                        command.arguments[i + 1], (AstRoot, AstJson)
                    ):
                        self.index[file_type].add_definition(
                            resolved_path,
                            self.source_path,
                            (argument.location, argument.end_location),
                        )
                    # If the pattern isn't matched then just treat it as a reference
                    # and not a definition of thre resource
                    else:
                        self.index[file_type].add_reference(
                            resolved_path,
                            self.source_path,
                            (argument.location, argument.end_location),
                        )

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
            case "predicate":
                add_representation(value, Predicate)


@dataclass
class Indexer(MutatingReducer):
    ctx: LanguageServerContext = required_field()
    resource_location: str = required_field()
    source_path: str = required_field()
    file_instance: Function | Module = required_field()

    output_ast: AstRoot = extra_field(
        default=AstRoot(commands=AstChildren(children=[]))
    )

    def __call__(self, ast: AstRoot, *args) -> AbstractNode:
        project_index = ProjectIndex.get(self.ctx)

        mecha = self.ctx.inject(Mecha)
        runtime = self.ctx.inject(Runtime)
        module = runtime.modules.get(self.file_instance)

        # A file always defines itself
        source_type = type(self.file_instance)
        project_index.remove_associated(self.source_path)

        project_index[source_type].add_definition(
            self.resource_location, self.source_path
        )

        # TODO: See if these steps can be merged into one

        # Attaches the type annotations for assignments
        initial_values = InitialStep()

        # The binding step is responsible for attaching the majority of type annotations
        bindings = BindingStep(
            index=project_index,
            source_path=self.source_path,
            module=module,
            runtime=self.ctx.inject(Runtime),
            mecha=self.ctx.inject(Mecha),
            # argument parser to resource type
            parser_to_file_type={
                "minecraft:advancement": Advancement,
                "minecraft:function": Function,
                "minecraft:predicate": Predicate,
                "minecraft:loot_table": LootTable,
            },
        )

        # This has to been done through extension because i'm too lazy to shadow or patch it
        self.extend(
            NestedLocationTransformer(
                nested_location_resolver=NestedLocationResolver(ctx=self.ctx)
            )
        )

        steps: list[Callable[[AstRoot], AstRoot]] = [
            initial_values,
            super().__call__,
            bindings,
        ]

        for step in steps:
            try:
                ast = step(ast)
            except CompilationError as e:
                raise e.__cause__
            except Exception as e:
                tb = "\n".join(traceback.format_tb(e.__traceback__))
                logging.error(f"Error occured during {step}\n{e}\n{tb}")

        self.output_ast = ast

        # Return a deepcopy so subsequent compilation steps don't modify the parsed state
        return deepcopy(ast)
