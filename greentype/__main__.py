import ast
from collections import defaultdict
import os
import logging
import argparse
import sys
import heapq
import itertools

from greentype import ast_utils
from greentype import utils


root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)

console_err = logging.StreamHandler(stream=sys.stderr)
console_err.setLevel(logging.WARNING)

console_info = logging.StreamHandler(stream=sys.stdout)
console_info.setFormatter(logging.Formatter('%(message)s'))
console_info.addFilter(lambda x: x.levelno < logging.WARNING)

root_logger.addHandler(console_err)
root_logger.addHandler(console_info)

LOG = logging.getLogger(__name__)

# TODO: get rid of global state
_classes_index = {}
_class_attributes = defaultdict(set)
_functions_index = {}
_modules = {}
_src_roots = []


class Definition:
    def __init__(self, qname, node):
        self.qname = qname
        self.node = node

    @property
    def name(self):
        parts = self.qname.rsplit('.', maxsplit=1)
        return parts[1] if len(parts) > 0 else parts[0]



class ClassDefinition(Definition):
    def __init__(self, qname, node, bases, members):
        super().__init__(qname, node)
        self.bases = bases
        self.attributes = members


class FunctionDefinition(Definition):
    def __init__(self, qname, node, parameters=None):
        super().__init__(qname, node)
        if parameters is None:
            self.parameters = []
        else:
            self.parameters = parameters

    @property
    def unbound_parameters(self):
        # outer_class = ast_utils.find_parent(self.node, ast.ClassDef, stop_cls=ast.FunctionDef, strict=True)
        # if outer_class is not None:
        if self.parameters and self.parameters[0].name == 'self':
            return self.parameters[1:]
        return self.parameters


class Parameter:
    def __init__(self, name, attributes, function):
        super().__init__()
        self.name = name
        self.attributes = attributes
        self.function = function


class ModuleVisitor(ast.NodeVisitor):
    def __init__(self, module_path):
        super().__init__()
        self.module_path = module_path
        self.module_name = utils.module_path_to_name(module_path)

    def qualified_name(self, node):
        scopes = ast_utils.find_parents(node, cls=(ast.FunctionDef, ast.ClassDef))
        prefix = '.'.join(ast_utils.node_name(scope) for scope in scopes)
        name = ast_utils.node_name(node)
        if prefix:
            name = prefix + '.' + name
        if self.module_name:
            name = self.module_name + '.' + name
        return name

class StructuralType:
    def __init__(self, attributes):
        self.attributes = attributes

    def __str__(self):
        return '{{{}}}'.format(', '.join(self.attributes))


class AttributesCollector(ast.NodeVisitor):
    """Collect accessed attributes for specified qualifier."""

    def collect(self, node):
        self.attributes = set()
        self.visit(node)
        return self.attributes

    def visit(self, node):
        if isinstance(node, list):
            for stmt in node:
                self.visit(stmt)
        else:
            super().visit(node)


class SimpleAttributesCollector(AttributesCollector):
    """Collect only immediately accessed attributes for qualifier.

    No alias or scope analysis is used. Operators and other special methods
    are considered, hover subscriptions are.
    """

    def __init__(self, name, read_only=True):
        super().__init__()
        self.name = name
        self.read_only = read_only

    def visit_Attribute(self, node):
        if isinstance(node.value, ast.Name) and node.value.id == self.name:
            if isinstance(node.ctx, ast.Load) or not self.read_only:
                self.attributes.add(node.attr)
        else:
            self.visit(node.value)


    def visit_Subscript(self, node):
        if isinstance(node.value, ast.Name) and node.value.id == self.name:
            if isinstance(node.ctx, ast.Load):
                self.attributes.add('__getitem__')
            elif not self.read_only:
                if isinstance(node.ctx, ast.Store):
                    self.attributes.add('__setitem__')
                elif isinstance(node.ctx, ast.Del):
                    self.attributes.add('__delitem__')


class FunctionVisitor(ModuleVisitor):
    def visit_FunctionDef(self, node):
        function_name = self.qualified_name(node)

        param_names = []
        param_names.extend(a.arg for a in node.args.args)
        if node.args.vararg:
            param_names.append(node.args.vararg)
        param_names.extend(a.arg for a in node.args.kwonlyargs)
        if node.args.kwarg:
            param_names.append(node.args.kwarg)

        definition = FunctionDefinition(function_name, node)
        for name in param_names:
            attributes = SimpleAttributesCollector(name).collect(node)
            definition.parameters.append(Parameter(name, attributes, definition))

        _functions_index[function_name] = definition


class ClassVisitor(ModuleVisitor):
    def visit_ClassDef(self, node):
        class_name = self.qualified_name(node)

        bases_names = []
        for expr in node.bases:
            base_name = ast_utils.attributes_chain_to_name(expr)
            if base_name is None:
                LOG.warning('Class %s in module %s uses computed bases. Not supported.', class_name, self.module_path)
                continue
            bases_names.append(base_name)

        # Only top-level functions and assignments are inspected
        class ClassAttributeCollector(AttributesCollector):
            def visit_FunctionDef(self, func_node):
                self.attributes.add(func_node.name)
                if ast_utils.node_name(func_node) == '__init__':
                    self_attributes = SimpleAttributesCollector('self', read_only=False).collect(func_node)
                    self.attributes.update(self_attributes)

            def visit_Assign(self, assign_node):
                target = assign_node.targets[0]
                if isinstance(target, ast.Name):
                    self.attributes.add(target.id)

        class_attributes = ClassAttributeCollector().collect(node)

        _classes_index[class_name] = ClassDefinition(class_name, node, bases_names, class_attributes)


def analyze_module(path):
    LOG.debug('Analyzing {!r}'.format(path))
    with open(path) as f:
        root_node = ast.parse(f.read())
        ast_utils.interlink_ast(root_node)
        ClassVisitor(path).visit(root_node)
        FunctionVisitor(path).visit(root_node)


def analyze(path):
    if os.path.isfile(path):
        if not utils.is_python_source_module(path):
            raise ValueError('Not a Python module {!r} (should end with .py).'.format(path))
        analyze_module(path)
    elif os.path.isdir(path):
        for dirpath, dirnames, filenames in os.walk(path):
            for name in dirnames:
                abs_path = os.path.abspath(os.path.join(dirpath, name))
                if not os.path.exists(os.path.join(abs_path, '__init__.py')):
                    # ignore namespace packages for now
                    LOG.debug('Not a package: %r. Skipping.', abs_path)
                    dirnames.remove(name)
            for name in filenames:
                abs_path = os.path.abspath(os.path.join(dirpath, name))
                if not utils.is_python_source_module(abs_path):
                    continue
                analyze_module(abs_path)

    if LOG.isEnabledFor(logging.INFO):
        LOG.info('Total: %d classes, %d functions', len(_classes_index), len(_functions_index))
        def find_most_busy_param(n, exclude_self):
            if exclude_self:
                params = itertools.chain.from_iterable(func.unbound_parameters for func in _functions_index.values())
            else:
                params = itertools.chain.from_iterable(func.parameters for func in _functions_index.values())

            most_used = heapq.nlargest(n, params, key=lambda x: len(x.attributes))
            lines = []
            for p in most_used:
                lines.append('{}#{}: {} times'.format(p.function.qname, p.name, len(p.attributes)))
            LOG.info('Most frequently used parameters (%d):\n  %s', n, '\n  '.join(lines))

            # LOG.info('Maximum referenced attributes %d: param %r, function %r',
            #          len(max_param.attributes), max_param.name, max_func.qualified_name)

        find_most_busy_param(20, exclude_self=True)
        # find_most_busy_param(10, exclude_self=False)
    LOG.debug('Functions:\n%s\n', '\n'.join(_functions_index))
    LOG.debug('Classes:\n%s\n', '\n'.join(_classes_index))


def main():
    sys.modules['greentype.__main__'] = sys.modules[__name__]

    parser = argparse.ArgumentParser()
    parser.add_argument('--src-roots',
                        help='Sources roots separated by colon. Used to resolve module names in project.')
    parser.add_argument('-v', '--verbose', action='store_true', help='Enable DEBUG logging.')
    parser.add_argument('path', help='Path to single Python module or directory.')
    args = parser.parse_args()

    if args.verbose:
        root_logger.setLevel(logging.DEBUG)

    try:
        target_path = os.path.abspath(os.path.expanduser(args.path))

        global _src_roots
        if not args.src_roots:
            if os.path.isfile(target_path):
                _src_roots = [os.path.dirname(target_path)]
            elif os.path.isdir(target_path):
                _src_roots = [target_path]
            else:
                raise ValueError('Unrecognized target {!r}. Should be either file or directory.'.format(target_path))
        else:
            _src_roots = args.src_roots.split(':')
        analyze(target_path)
    except Exception as e:
        LOG.exception(e)


if __name__ == '__main__':
    main()
