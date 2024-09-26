
import logging
from tokenstream import SourceLocation
from mecha import AstNode


def get_node_at_position(root: AstNode, target: SourceLocation):
    nearest_node = root
    for node in root.walk():
        start = node.location
        end = node.end_location

        if not (start.colno <= target.colno and end.colno >= target.colno):
            continue

        if not (start.lineno == target.lineno and end.lineno == target.lineno):
            continue

        if start.pos >= nearest_node.location.pos and end.pos <= nearest_node.end_location.pos:
            nearest_node = node

    return nearest_node