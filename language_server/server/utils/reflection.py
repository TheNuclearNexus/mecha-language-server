import inspect
import logging
import types
import typing
from dataclasses import dataclass, field, fields, is_dataclass
from typing import Any, get_origin

UNKNOWN_TYPE = object()
TYPE_TO_INFO: dict[type, "TypeInfo"] = {}


@dataclass
class ParameterInfo:
    annotation: Any
    default: Any


@dataclass
class FunctionInfo:
    parameters: list[tuple[str, ParameterInfo]]
    return_annotation: Any
    doc: str | None

    @staticmethod
    def from_signature(
        signature: inspect.Signature, doc: str | None, hints: dict[str, Any]
    ) -> "FunctionInfo":
        return FunctionInfo(
            parameters=[
                (
                    name,
                    ParameterInfo(
                        annotation=parameter.annotation, default=parameter.default
                    ),
                )
                for name, parameter in signature.parameters.items()
            ],
            return_annotation=hints.get("return") or signature.return_annotation,
            doc=doc,
        )

    @staticmethod
    def extract(field_value: Any):
        try:
            hints = typing.get_type_hints(field_value)
            logging.debug(hints)
            signature = inspect.signature(field_value)
            return FunctionInfo.from_signature(signature, field_value.__doc__, hints)
        except Exception as e:
            return FunctionInfo(
                parameters=[
                    (
                        "???",
                        ParameterInfo(inspect.Parameter.empty, inspect.Parameter.empty),
                    )
                ],
                return_annotation="???",
                doc="Error while extracting signature: " + str(e),
            )


@dataclass
class TypeInfo:
    fields: dict[str, Any] = field(default_factory=dict)
    functions: dict[str, FunctionInfo] = field(default_factory=dict)

    def get_member(self, field_name: str) -> Any | FunctionInfo:
        return self.fields.get(field_name) or self.functions.get(field_name)

    def add_member(
        self,
        field_annotations: dict[str, Any],
        field_name: str,
        field_value: Any,
        skip_fields=False,
    ):
        if (
            inspect.isfunction(field_value)
            or inspect.ismethod(field_value)
            or inspect.ismethoddescriptor(field_value)
            or inspect.isbuiltin(field_value)
        ):
            self.functions[field_name] = FunctionInfo.extract(field_value)

        elif skip_fields:
            return
        elif field_name in field_annotations:
            self.fields[field_name] = field_annotations[field_name]
        elif _ := get_origin(field_value):
            self.fields[field_name] = field_value
        else:
            self.fields[field_name] = type(field_value)


def get_type_info(_type: type) -> TypeInfo:
    if _type in TYPE_TO_INFO:
        return TYPE_TO_INFO[type]

    info = TypeInfo()

    # logging.debug("\n\n")
    # logging.debug("-" * 50)
    # logging.debug("Indexing type " + _type.__name__)

    field_annotations = (
        inspect.get_annotations(_type)
        if inspect.isclass(_type) or callable(_type) or inspect.ismodule(_type)
        else {}
    )

    if is_dataclass(_type):
        for field in fields(_type):
            info.add_member({}, field.name, field.type)
            # logging.debug(f"{field.name}, {type(field.type)}")

    for field_name in dir(_type):
        field_value = getattr(_type, field_name)
        # logging.debug(f"{field_name}, {field_value}")
        info.add_member(
            field_annotations, field_name, field_value, skip_fields=is_dataclass(_type)
        )

    # logging.debug("-" * 50)
    # logging.debug("\n\n")
    # logging.debug(info)
    return info


def get_name_of_type(annotation):
    if annotation is inspect.Parameter.empty:
        return None

    if annotation is types.NoneType:
        return "None"

    if annotation is UNKNOWN_TYPE:
        return "???"

    origin = typing.get_origin(annotation)
    args = list(map(str, map(get_name_of_type, typing.get_args(annotation))))

    if origin is typing.Union or origin is types.UnionType:
        return " | ".join(args)
    elif origin:
        return f"{origin.__name__}[{', '.join(args)}]"

    try:
        return annotation.__repr__()
    except:
        return annotation.__name__ if hasattr(annotation, "__name__") else annotation


def format_function_hints(name: str, signature: FunctionInfo, keyword: str = "def"):
    hint = f"{keyword} {name}("

    return_type = signature.return_annotation

    parameters = []

    for name, parameter in signature.parameters:
        annotation = get_name_of_type(parameter.annotation)

        if annotation is None and parameter.default is not inspect.Parameter.empty:
            annotation = get_name_of_type(type(parameter.default))

        annotation_string = ": " + str(annotation) if annotation else ""
        default_string = (
            " = " + parameter.default.__repr__()
            if parameter.default is not inspect.Parameter.empty
            else ""
        )

        parameters.append(f"\n\t{name}{annotation_string}{default_string}")

    hint += ",".join(parameters)

    hint += f"\n) -> {get_name_of_type(return_type)}"

    return hint
