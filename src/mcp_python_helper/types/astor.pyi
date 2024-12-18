from ast import AST
from collections.abc import Callable

def to_source(
    node: AST,
    indent_with: str = " " * 4,
    add_line_information: bool = False,
    pretty_string: Callable[[str], str] = lambda x: x,
    pretty_source: Callable[[str], str] = lambda x: x,
    source_generator_class: type | None = None,
) -> str: ...
