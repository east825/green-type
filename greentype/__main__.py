import ast
import os
import logging
import argparse
import sys

import greentype.nodes as nodes
from greentype.utils import path_to_name, is_python_source_module


logging.basicConfig(level=logging.DEBUG)

LOG = logging.getLogger(__name__)

# TODO: get rid of global state
_classes = {}
_modules = {}
_src_roots = []


class _ModuleVisitor(ast.NodeVisitor):
    def __init__(self, module_path):
        super().__init__()
        self.module_path = module_path


class _AttributesCollector(ast.NodeVisitor):
    """Collect accessed attributes for specified qualifier."""

    def __init__(self, name, read_only=True):
        super().__init__()
        self.name = name
        self.attributes = []
        self.read_only = read_only

    def collect(self, node):
        self.attributes = []
        self.visit(node)
        return self.attributes


class _SimpleAttributesCollector(_AttributesCollector):
    """Collect only immediately accessed attributes for qualifier.

    No alias or scope analysis is used. Operators and other special methods
    are considered, hover subscriptions are.
    """

    def visit_Attribute(self, node):
        if isinstance(node.expr, ast.Name) and node.expr.id == self.name:
            if not self.read_only or node.ctx == ast.Load:
                self.attributes.append(node.attr)


    def visit_Subscript(self, node):
        if isinstance(node.value, ast.Name) and node.value.id == self.name:
            if isinstance(node.ctx, ast.Load):
                self.attributes.append('__getitem__')
            elif not self.read_only:
                if isinstance(node.ctx, ast.Store):
                    self.attributes.append('__setitem__')
                elif isinstance(node.ctx, ast.Del):
                    self.attributes.append('__delitem__')


class _FunctionVisitor(_ModuleVisitor):
    def visit_FunctionDef(self, func_node):
        param_names = []
        param_names.extend(a.arg for a in func_node.args.args)
        param_names.extend(a.arg for a in func_node.args.kwonlyargs)

        param_aliases = {name: {name} for name in param_names}
        param_attributes = {name: set() for name in param_names}

        class Collector(ast.NodeVisitor):
            def visit_Assign(self, assignment_node):
                # for now without tuple packing/unpacking
                target, expr = assignment_node.targets[0], assignment_node.value
                # collect usages before assignment
                self.visit(expr)
                # TODO: find out when targets in AST is actually not a single element list
                if isinstance(expr, (ast.List, ast.Tuple)) and isinstance(target, (ast.List, ast.Tuple)) \
                        and len(target.elts) == len(expr.elts):
                    for target, expr in zip(target.elts, expr.elts):
                        self._process_assignment(target, expr)
                elif isinstance(target, ast.Name):
                    self._process_assignment(target, expr)


            def _process_assignment(self, target, expr):
                if isinstance(target, ast.Name) and isinstance(expr, ast.Name):
                    for param, aliases in param_aliases.items():
                        updated = set(aliases)
                        if expr.id in aliases:
                            updated.add(target.id)
                        if target.id in aliases:
                            updated.remove(target.id)
                        param_aliases[param] = updated

            def visit_Attribute(self, attr_node):
                qualifier, attr_name = attr_node.value, attr_node.attr
                if isinstance(qualifier, ast.Name):
                    for param, aliases in param_aliases.items():
                        if qualifier.id in aliases:
                            param_attributes[param].add(attr_name)

            def visit_Subscript(self, subscript_node):
                qualifier, access = subscript_node.value, subscript_node.ctx
                if isinstance(qualifier, ast.Name):
                    for param, aliases in param_aliases.items():
                        if qualifier.id in aliases:
                            # What the heck is AugLoad / AugStore / Param
                            if isinstance(access, ast.Load):
                                param_attributes[param].add('__getitem__')
                            elif isinstance(access, ast.Store):
                                param_attributes[param].add('__setitem__')
                            elif isinstance(access, ast.Del):
                                param_attributes[param].add('__delitem__')


        for stmt in func_node.body:
            Collector().visit(stmt)

        param_types = []
        for name in param_names:
            param_types.append('{} :: {{{}}}'.format(name, ', '.join(param_attributes[name])))
        LOG.debug('{}({})'.format(func_node.name, ', '.join(param_types)))


class _ClassVisitor(_ModuleVisitor):
    def visit_ClassDef(self, class_node):
        bases_names = []
        for expr in class_node.bases:
            parts = []
            while True:
                if isinstance(expr, ast.Name):
                    parts.append(expr.id)
                    break
                elif isinstance(expr, ast.Attribute):
                    parts.append(expr.attr)
                    expr = expr.value
                else:
                    LOG.warning('Class {} in module {} uses computed bases. Not supported.')
                    break
            if parts:
                bases_names.append('.'.join(reversed(parts)))

        attrs = []
        # TODO: collect attributes in constructor and other methods
        class ClassAttributeVisitor(ast.NodeVisitor):
            def visit_FunctionDef(self, func_node):
                attrs.append(func_node.name)

            def visit_Assign(self, assign_node):
                target = assign_node.targets[0]
                if isinstance(target, ast.Name):
                    attrs.append(target.id)

        for stmt in class_node.body:
            ClassAttributeVisitor().visit(stmt)

        global _classes
        qname = '{}.{}'.format(path_to_name(self.module_path), class_node.name)
        class_def = nodes.ClassDefinitionNode(qname, bases_names, attrs)
        _classes[qname] = class_def


def analyze_module(path):
    LOG.info('Analyzing {!r}'.format(path))
    with open(path) as f:
        root_node = ast.parse(f.read())
        _ClassVisitor(path).visit(root_node)
        _FunctionVisitor(path).visit(root_node)


def analyze(path):
    if os.path.isfile(path):
        if not is_python_source_module(path):
            raise ValueError('Not a Python module {!r} (should end with .py).'.format(path))
        analyze_module(path)
    elif os.path.isdir(path):
        for dirpath, dirnames, filenames in os.walk(path):
            for name in dirnames:
                abs_path = os.path.abspath(os.path.join(dirpath, name))
                if not os.path.exists(os.path.join(abs_path, '__init__.py')):
                    # ignore namespace packages for now
                    LOG.debug('Not a package: {!r}. Skipping.'.format())
                    dirnames.remove(name)
            for name in filenames:
                abs_path = os.path.abspath(os.path.join(dirpath, name))
                if not is_python_source_module(abs_path):
                    continue
                analyze_module(abs_path)

    if LOG.isEnabledFor(logging.DEBUG):
        LOG.debug('Classes found:\n' + '\n'.join(map(str, _classes.values())))


def main():
    sys.modules['greentype.__main__'] = sys.modules[__name__]

    parser = argparse.ArgumentParser()
    parser.add_argument('--src-roots',
                        help='Sources roots separated by colon. Used to resolve module names in project.')
    parser.add_argument('path', help='Path to single Python module or directory.')
    args = parser.parse_args()

    try:
        target_path = os.path.abspath(args.path)

        global _src_roots
        if not args.src_roots:
            if os.path.isfile(target_path):
                _src_roots = [os.path.dirname(target_path)]
            elif os.path.isdir(target_path):
                _src_roots = [target_path]
            else:
                raise ValueError('Unrecognized target {!r}. Should be either file or directory.')
        else:
            _src_roots = args.src_roots.split(':')
        analyze(target_path)
    except Exception as e:
        LOG.exception(e)


if __name__ == '__main__':
    main()
