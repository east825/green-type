import ast
import weakref


def attributes_chain_to_name(node):
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return '.'.join(reversed(parts))
    else:
        return None


def node_name(node):
    return getattr(node, 'id', None) or getattr(node, 'name', None)


def interlink_ast(root):
    parents_stack = []

    def transform(node):
        if isinstance(node, ast.AST):
            if parents_stack:
                # TODO: may be better to use weakref here
                # node.parent = weakref.ref(parents_stack[-1])
                # node.parent = property(fget=lambda x: node._parent())
                node.parent = parents_stack[-1]
            else:
                node.parent = None
            parents_stack.append(node)
            for child in ast.iter_child_nodes(node):
                transform(child)
            parents_stack.pop()

    transform(root)


def find_parent(node, cls, stop_cls=ast.Module, strict=True):
    if strict and node is not None:
        node = getattr(node, 'parent', None)

    while node and not isinstance(node, stop_cls):
        if isinstance(node, cls):
            return node
        node = getattr(node, 'parent', None)
    return None


def find_parents(node, cls, stop_cls=ast.Module, strict=True):
    if strict and node is not None:
        node = getattr(node, 'parent', None)

    parents = []
    while node and not isinstance(node, stop_cls):
        if isinstance(node, cls):
            parents.append(node)
        node = getattr(node, 'parent', None)
    return reversed(parents)






