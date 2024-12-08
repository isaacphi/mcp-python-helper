import ast
import astor


class NodeFinder(ast.NodeVisitor):
    def __init__(self, search):
        self.path = search.split(".")
        self.search = search
        self.found_nodes = []
        self.current_class = None

    def visit_ClassDef(self, node):
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

    def visit_FunctionDef(self, node):
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

    def generic_visit(self, node):
        if hasattr(node, "lineno") and isinstance(node, ast.stmt):
            try:
                node_text = " ".join(astor.to_source(node).strip().split())
                search_text = " ".join(self.search.strip().split())
                if node_text == search_text:
                    self.found_nodes.append(node)
            except:
                pass
        super().generic_visit(node)


def find_nodes(tree, search):
    finder = NodeFinder(search)
    finder.visit(tree)
    return finder.found_nodes


def find_in_file(filename, search):
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


class NodeModifier(ast.NodeTransformer):
    def __init__(self, target_node, new_code, position="replace"):
        self.target_node = target_node
        self.new_node = ast.parse(new_code).body[0]
        self.position = position
        self.stop_after_found = True
        self.skip_next = False

    def visit(self, node):
        if self.skip_next:
            self.skip_next = False
            return node
        if node == self.target_node:
            if self.position == "replace":
                return self.new_node
            elif self.position == "before":
                if isinstance(node.parent, ast.Module):
                    self.skip_next = True
                    idx = node.parent.body.index(node)
                    node.parent.body.insert(idx, self.new_node)
                return self.new_node
            elif self.position == "after":
                if isinstance(node.parent, ast.Module):
                    idx = node.parent.body.index(node)
                    node.parent.body.insert(idx + 1, self.new_node)
                return node
        return self.generic_visit(node)


def modify_in_file(filename, search, new_code, position="replace"):
    with open(filename, "r") as f:
        source = f.read()
        tree = ast.parse(source)

    # Add parent references
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            child.parent = parent

    nodes = find_nodes(tree, search)
    if not nodes:
        return False

    for node in nodes:
        modifier = NodeModifier(node, new_code, position)
        tree = modifier.visit(tree)

    modified_source = astor.to_source(tree)
    with open(filename, "w") as f:
        f.write(modified_source)
    return True


# results = find_in_file("example.py", "test = False")
# for result in results:
#     print(f"Found at {result['filename']}:{result['line']}:{result['column']}")

modify_in_file("example.py", "my_method", "import os", "replace")
