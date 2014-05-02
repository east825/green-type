from collections.abc import Iterable
import ast
import sys
import collections

INDENT_SIZE = 2


def main(path):
    with open(path) as f:
        print(dump_ast(ast.parse(f.read(), path)))
        # visitor = DumpVisitor()
        # visitor.visit(ast.parse(f.read(), path))
        # visitor.dump()


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


def is_collection(x):
    return isinstance(x, Iterable) and not isinstance(x, (str, bytes))


def dump_ast(node, indent=0):
    first_line = ' ' * indent + format_node(node)
    child_lines = []
    for name, value in ast.iter_fields(node):
        child_indent = ' ' * (indent + INDENT_SIZE)
        if isinstance(value, ast.AST):
            field_fmt = dump_ast(value, indent + INDENT_SIZE)
            child_lines.append('{}{}: {}'.format(child_indent, name, field_fmt.lstrip()))
        elif is_collection(value):
            child_lines.append('{}{}: *'.format(child_indent, name))
            child_lines.extend(dump_ast(c, indent + INDENT_SIZE * 2) for c in value)
        else:
            child_lines.append('{}{}: {!r}'.format(child_indent, name, value))
    if child_lines:
        return first_line + '\n' + '\n'.join(child_lines)
    return first_line


class DumpVisitor(ast.NodeVisitor):
    def __init__(self, increment=INDENT_SIZE):
        super().__init__()
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


if __name__ == '__main__':
    main(sys.argv[1])
