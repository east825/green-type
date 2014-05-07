from collections.abc import Iterable
import ast
import logging
import os
import sys
import collections

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


def is_collection(x):
    return isinstance(x, Iterable) and not isinstance(x, (str, bytes))


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


def camel_to_snake(s):
    """Translate CamelCase identifier to snake_case.

    If identifier is already in snake case it will be returned unchanged,
    except that leading and trailing underscores will be stripped.
    """
    words = []
    word = []
    prev_upper = False
    for c in s:
        if ((c.isupper() and not prev_upper) or not c.isalnum()) and word:
            words.append(''.join(word))
            word = []
        if c.isalnum():
            word.append(c.lower())
            prev_upper = c.isupper()
    if word:
        words.append(''.join(word))
    return '_'.join(words)


def module_path_to_name(path):
    from greentype.__main__ import _src_roots

    path = os.path.abspath(path)
    for src_root in _src_roots + sys.path:
        if path.startswith(src_root):
            relative = os.path.relpath(path, src_root)
            transformed, _ = os.path.splitext(relative)
            dir_name, base_name = os.path.split(transformed)
            if base_name == '__init__':
                transformed = dir_name
            return transformed.replace(os.path.sep, '.').strip('.')
    raise ValueError('Unresolved module {!r}'.format(path))


def is_python_source_module(path):
    _, ext = os.path.splitext(path)
    # importlib.machinery.SOURCE_SUFFIXES?
    return os.path.isfile(path) and ext == '.py'



def main(path):
    with open(path) as f:
        root_node = ast.parse(f.read(), path)
        # print(ast.dump(root_node, include_attributes=True))
        print(dump_ast(root_node))
        # visitor = DumpVisitor()
        # visitor.visit(ast.parse(f.read(), path))
        # visitor.dump()


if __name__ == '__main__':
    main(sys.argv[1])
