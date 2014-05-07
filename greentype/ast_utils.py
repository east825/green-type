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

def node_parent(node):
    parent = getattr(node, '_parent', None)
    return parent() if parent is not None else None


def interlink_ast(root):
    parents_stack = []

    def transform(node):
        if isinstance(node, ast.AST):
            if parents_stack:
                # TODO: may be better to use weakref here
                node._parent = weakref.ref(parents_stack[-1])
                # property can't be defined outside of class, because invoked via
                # __getattribute__ machinery
                # and unfortunately ast.AST can't be patched either ;)
                # node.parent = property(fget=lambda x: node._parent())
                # node._parent = parents_stack[-1]
            else:
                node._parent = None
            parents_stack.append(node)
            for child in ast.iter_child_nodes(node):
                transform(child)
            parents_stack.pop()

    transform(root)


def find_parent(node, cls, stop_cls=ast.Module, strict=True):
    if strict and node is not None:
        node = node_parent(node)

    while node and not isinstance(node, stop_cls):
        if isinstance(node, cls):
            return node_parent(node)
    return None


def find_parents(node, cls, stop_cls=ast.Module, strict=True):
    if strict and node is not None:
        node = node_parent(node)

    parents = []
    while node and not isinstance(node, stop_cls):
        if isinstance(node, cls):
            parents.append(node)
        node = node_parent(node)
    return reversed(parents)






