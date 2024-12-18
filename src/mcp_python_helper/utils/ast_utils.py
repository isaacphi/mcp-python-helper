from typing import Any, Dict, List
import ast
import astor


class TargetNotFound(Exception):
    pass


class MultipleTargetsFound(Exception):
    pass


class InvalidPosition(Exception):
    pass


class NodeFinder(ast.NodeVisitor):
    def __init__(self, search: str):
        self.path = search.split(".")
        self.search = search
        self.found_nodes: List[ast.AST] = []
        self.current_class: ast.ClassDef | None = None

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        if node.name == self.path[0]:
            if len(self.path) == 1:
                self.found_nodes.append(node)
            else:
                prev_class = self.current_class
                self.current_class = node
                self.generic_visit(node)
                self.current_class = prev_class
        else:
            self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        if (
            len(self.path) == 2
            and self.current_class
            and self.current_class.name == self.path[0]
            and node.name == self.path[1]
        ):
            self.found_nodes.append(node)
        elif len(self.path) == 1 and node.name == self.path[0]:
            self.found_nodes.append(node)
        self.generic_visit(node)

    def generic_visit(self, node: ast.AST) -> None:
        if hasattr(node, "lineno") and isinstance(node, ast.stmt):
            try:
                node_text = " ".join(astor.to_source(node).strip().split())
                search_text = " ".join(self.search.strip().split())
                if node_text == search_text:
                    self.found_nodes.append(node)
            except Exception:
                pass
        super().generic_visit(node)


class NodeModifier(ast.NodeTransformer):
    def __init__(self, target_node: ast.AST, new_code: str, position: str = "replace"):
        self.target_node = target_node
        self.new_node = ast.parse(new_code).body[0]
        self.position = position
        self.skip_next = False

    def visit(self, node: ast.AST) -> ast.AST:
        if self.skip_next:
            self.skip_next = False
            return node
        if node == self.target_node:
            if self.position == "replace":
                return self.new_node
            elif self.position == "before":
                self.skip_next = True
                idx = node.parent.body.index(node)  # type: ignore
                node.parent.body.insert(idx, self.new_node)  # type: ignore
                return self.new_node
            elif self.position == "after":
                if isinstance(node.parent, ast.Module):
                    idx = node.parent.body.index(node)
                    node.parent.body.insert(idx + 1, self.new_node)
                return node
            else:
                raise InvalidPosition("Invalid position")
        return self.generic_visit(node)


def find_nodes(tree: ast.AST, search: str) -> List[ast.AST]:
    finder = NodeFinder(search)
    finder.visit(tree)
    return finder.found_nodes


def find_in_file(filename: str, search: str) -> List[Dict[str, Any]]:
    with open(filename, "r") as f:
        tree = ast.parse(f.read(), filename)
    nodes = find_nodes(tree, search)
    return [
        {
            "node": node,
            "line": node.lineno,
            "column": node.col_offset,
            "filename": filename,
        }
        for node in nodes
        if hasattr(node, "lineno")
    ]


def modify_source(source: str, new_code: str, target: str, position: str) -> str:
    tree = ast.parse(source)

    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            child.parent = parent  # type: ignore

    nodes = find_nodes(tree, target)
    if not nodes:
        raise TargetNotFound("Target not found")

    if len(nodes) > 1:
        raise MultipleTargetsFound(f"{len(nodes)} targets found")

    for node in nodes:
        modifier = NodeModifier(node, new_code, position)
        tree = modifier.visit(tree)

    return astor.to_source(tree)