import ast
import weakref
import sys
import collections
from greentype.utils import is_collection


def decorated_with(node, name):
    if not isinstance(node, (ast.ClassDef, ast.FunctionDef)):
        raise ValueError('Illegal node type "{}". Should be either class '
                         'or function definition.'.format(type(node).__name__))

    decorators = [attributes_chain_to_name(d) for d in node.decorator_list]
    return name in decorators


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


INDENT_SIZE = 2


def format_node(node, include_fields=False):
    fields = collections.OrderedDict()
    fields['line'] = getattr(node, 'lineno', '<unknown>')
    fields['col'] = getattr(node, 'col_offset', '<unknown>')
    if include_fields:
        for field_name, field in ast.iter_fields(node):
            if not isinstance(field, ast.AST) and not is_collection(field):
                fields[field_name] = field
    formatted_pairs = ['{}={!r}'.format(k, v) for k, v in fields.items()]
    return '{}({})'.format(type(node).__name__, ' '.join(formatted_pairs))


def dump_ast(node, indent=0):
    if isinstance(node, ast.AST):
        first_line = ' ' * indent + format_node(node)
        child_lines = []
        for name, value in ast.iter_fields(node):
            child_indent = ' ' * (indent + INDENT_SIZE)
            if is_collection(value):
                child_lines.append('{}{}: *'.format(child_indent, name))
                child_lines.extend(dump_ast(c, indent + INDENT_SIZE * 2) for c in value)
            else:
                field_fmt = dump_ast(value, indent + INDENT_SIZE)
                child_lines.append('{}{}: {}'.format(child_indent, name, field_fmt.lstrip()))
        if child_lines:
            return first_line + '\n' + '\n'.join(child_lines)
        return first_line
    else:
        return '{}{!r}'.format(' ' * indent, node)


class DumpVisitor(ast.NodeVisitor):
    def __init__(self, increment=INDENT_SIZE):
        super(DumpVisitor, self).__init__()
        self.increment = increment
        self.lines = []
        self.indent = 0

    def visit(self, node):
        self.lines.append(' ' * self.indent + format_node(node, True))
        self.indent += self.increment
        self.generic_visit(node)
        self.indent -= self.increment

    def dump(self):
        print(self.dumps())

    def dumps(self):
        return '\n'.join(self.lines)


def main(path):
    with open(path) as f:
        root_node = ast.parse(f.read(), path)
        # print(ast.dump(root_node, include_attributes=True))
        print(dump_ast(root_node))
        # visitor = DumpVisitor()
        # visitor.visit(ast.parse(f.read(), path))
        # visitor.dump()


class GeneratorVisitor(object):
    def visit(self, node):
        if isinstance(node, ast.AST):
            method_name = 'visit_' + node.__class__.__name__
            for value in getattr(self, method_name, self.generic_visit)(node):
                yield value


    def generic_visit(self, node):
        for node in ast.iter_child_nodes(node):
            for value in self.visit(node):
                yield value


if __name__ == '__main__':
    main(sys.argv[1])






