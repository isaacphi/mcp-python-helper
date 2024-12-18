import ast
from typing import Any, Optional, cast

import astor


class TargetNotFoundError(Exception):
    pass


class MultipleTargetsFoundError(Exception):
    pass


class InvalidPositionError(Exception):
    pass


# Add parent attribute to ast.AST
class ExtendedAST(ast.AST):
    parent: Optional["ExtendedAST"] = None
    lineno: int = 0
    col_offset: int = 0


class NodeFinder(ast.NodeVisitor):
    def __init__(self, search: str):
        self.path = search.split(".")
        self.search = search
        self.found_nodes: list[ast.AST | ExtendedAST] = []
        self.current_class: ast.ClassDef | None = None

    def visit_ClassDef(self, node: ast.ClassDef) -> None:  # noqa: N802
        if node.name == self.path[0]:
            if len(self.path) == 1:
                self.found_nodes.append(cast(ExtendedAST, node))
            else:
                prev_class = self.current_class
                self.current_class = node
                self.generic_visit(node)
                self.current_class = prev_class
        else:
            self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
        if (
            len(self.path) == 2
            and self.current_class
            and self.current_class.name == self.path[0]
            and node.name == self.path[1]
        ):
            self.found_nodes.append(cast(ExtendedAST, node))
        elif len(self.path) == 1 and node.name == self.path[0]:
            self.found_nodes.append(cast(ExtendedAST, node))
        self.generic_visit(node)

    def generic_visit(self, node: ast.AST) -> None:
        if hasattr(node, "lineno") and isinstance(node, ast.stmt):
            try:
                node_text = " ".join(astor.to_source(node).strip().split())
                search_text = " ".join(self.search.strip().split())
                if node_text == search_text:
                    self.found_nodes.append(cast(ExtendedAST, node))
            except Exception:
                pass
        super().generic_visit(node)


class NodeModifier(ast.NodeTransformer):
    def __init__(
        self,
        target_node: ast.AST | ExtendedAST,
        new_code: str,
        position: str = "replace",
    ):
        self.target_node = target_node
        parsed = ast.parse(new_code)
        self.new_node = parsed.body[0]
        self.position = position
        self.skip_next = False

    def visit(self, node: ast.AST | ExtendedAST) -> ast.AST:
        if self.skip_next:
            self.skip_next = False
            return node
        if node == self.target_node:
            if self.position == "replace":
                return self.new_node
            elif self.position == "before":
                self.skip_next = True
                parent = getattr(self.target_node, "parent", None)
                if parent and isinstance(parent, ast.Module):
                    if isinstance(node, ast.stmt):
                        idx = parent.body.index(node)
                        parent.body.insert(idx, self.new_node)
                return self.new_node
            elif self.position == "after":
                parent = getattr(self.target_node, "parent", None)
                if parent and isinstance(parent, ast.Module):
                    if isinstance(node, ast.stmt):
                        idx = parent.body.index(node)
                        parent.body.insert(idx + 1, self.new_node)
                return node
            else:
                raise InvalidPositionError("Invalid position")
        return self.generic_visit(node)


def find_nodes(tree: ast.AST, search: str) -> list[ast.AST | ExtendedAST]:
    finder = NodeFinder(search)
    finder.visit(tree)
    return finder.found_nodes


def find_in_file(filename: str, search: str) -> list[dict[str, Any]]:
    with open(filename) as f:
        tree = ast.parse(f.read(), filename)
    nodes = find_nodes(tree, search)
    return [
        {
            "node": node,
            "line": getattr(node, "lineno", 0),
            "column": getattr(node, "col_offset", 0),
            "filename": filename,
        }
        for node in nodes
        if hasattr(node, "lineno")
    ]


def modify_source(source: str, new_code: str, target: str, position: str) -> str:
    tree = ast.parse(source)

    # Add parent references to all nodes
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            child = cast(ExtendedAST, child)
            child.parent = cast(ExtendedAST, parent)

    nodes = find_nodes(tree, target)
    if not nodes:
        raise TargetNotFoundError("Target not found")

    if len(nodes) > 1:
        raise MultipleTargetsFoundError(f"{len(nodes)} targets found")

    for node in nodes:
        modifier = NodeModifier(node, new_code, position)
        tree = modifier.visit(tree)

    return astor.to_source(tree)
