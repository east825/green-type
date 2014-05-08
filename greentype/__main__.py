import ast
from collections import defaultdict
import functools
import inspect
import operator
import os
import logging
import argparse
import sys
import heapq
import itertools
import time

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
_functions_index = {}
_parameters_index = {}

_classes_index = {}
_class_attributes = defaultdict(set)

_modules = {}
_src_roots = []


class Stat:
    @staticmethod
    def total_functions():
        return len(_functions_index)

    @staticmethod
    def total_classes():
        return len(_classes_index)

    @staticmethod
    def total_attributes():
        return len(_class_attributes)

    @staticmethod
    def attributeless_parameters():
        return [p for p in _parameters_index.values() if not p.attributes]


    @staticmethod
    def undefined_parameters():
        return [p for p in _parameters_index.values() if not p.suggested_types]

    @staticmethod
    def scattered_parameters():
        return [p for p in _parameters_index.values() if len(p.suggested_types) > 1]

    @staticmethod
    def top_parameters_with_most_attributes(n, exclude_self=True):
        if exclude_self:
            params = itertools.chain.from_iterable(f.unbound_parameters for f in _functions_index.values())
        else:
            params = _parameters_index.values()
        return heapq.nlargest(n, params, key=lambda x: len(x.attributes))

    @staticmethod
    def top_parameters_with_scattered_types(n):
        return heapq.nlargest(n, Stat.scattered_parameters(), key=lambda x: len(x.suggested_types))

    @staticmethod
    def display(total=True, param_attributes=True, param_types=True,
                all_function=False, all_classes=False, all_params=False):
        max_params = 20
        if total:
            LOG.info('Total: %d classes, %d functions, %d class attributes',
                     Stat.total_classes(), Stat.total_functions(), Stat.total_attributes())
        if param_attributes:
            lines = []
            for p in Stat.top_parameters_with_most_attributes(max_params):
                lines.append('{:3} attributes: {}'.format(len(p.attributes), p))
            log_items(lines, 'Most frequently accessed parameters (top %d):', max_params)

        if param_types:
            total = len(_parameters_index)
            n_attributeless = len(Stat.attributeless_parameters())
            n_undefined = len(Stat.undefined_parameters())
            n_scattered = len(Stat.scattered_parameters())
            LOG.info('Total: %d parameters has no attributes (%.2f%%), '
                     '%d parameters has unknown type (%.2f%%), '
                     '%d parameters has scattered types (%.2f%%)',
                     n_attributeless, (n_attributeless / total) * 100,
                     n_undefined, (n_undefined / total) * 100,
                     n_scattered, (n_scattered / total) * 100)
            lines = []
            for p in Stat.top_parameters_with_scattered_types(max_params):
                lines.append('{:3} types: {}: {}'.format(len(p.suggested_types), p, p.suggested_types))
            log_items(lines, 'Parameters with scattered type (top %d):', max_params)

        if all_function:
            log_items(_functions_index.values(), 'Functions:')
        if all_classes:
            log_items(_classes_index.values(), 'Classes:')
        if all_params:
            log_items(_parameters_index.values(), 'Parameters:')



class Definition:
    def __init__(self, qname, node):
        self.qname = qname
        self.node = node

    @property
    def name(self):
        parts = self.qname.rsplit('#', maxsplit=1)
        if len(parts) == 1:
            parts = self.qname.rsplit('.', maxsplit=1)
        return parts[1] if len(parts) > 1 else parts[0]

    def __str__(self):
        return '{}({})'.format(type(self).__name__, self.qname)

    def __repr__(self):
        return str(self)

    def __eq__(self, other):
        return isinstance(other, Definition) and self.qname == other.qname

    def __ne__(self, other):
        return not (self == other)

    def __hash__(self):
        return hash(self.qname)


class ClassDefinition(Definition):
    def __init__(self, qname, node, bases, members):
        super().__init__(qname, node)
        self.bases = bases
        self.attributes = members

    def __str__(self):
        return 'class {}({})'.format(self.qname, ', '.join(self.bases))


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

    def __str__(self):
        return 'def {}({})'.format(self.qname, ''.join(p.name for p in self.parameters))


class Parameter(Definition):
    def __init__(self, qname, node, attributes, function):
        super().__init__(qname, node)
        self.attributes = attributes
        self.function = function
        self.suggested_types = set()

    def __str__(self):
        s = '{}::{}'.format(self.qname, StructuralType(self.attributes))
        if self.suggested_types:
            return '{} ~ {}'.format(s, self.suggested_types)
        return s


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

    def __repr__(self):
        return str(self)


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
        func_name = self.qualified_name(node)
        func_def = FunctionDefinition(func_name, node)

        for arg in itertools.chain(node.args.args, [node.args.vararg], node.args.kwonlyargs, [node.args.kwarg]):
            # *args and **kwargs may be None
            if arg is None:
                continue
            param_name = arg if isinstance(arg, str) else arg.arg
            attributes = SimpleAttributesCollector(param_name).collect(node)
            param_qname = func_name + '#' + param_name
            param_def = Parameter(param_qname, node, attributes, func_def)
            _parameters_index[param_qname] = param_def

            func_def.parameters.append(param_def)
        _functions_index[func_name] = func_def


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
        definition = ClassDefinition(class_name, node, bases_names, class_attributes)
        for attribute in class_attributes:
            _class_attributes[attribute].add(definition)
        _classes_index[class_name] = definition


def analyze_module(path):
    LOG.debug('Analyzing {!r}'.format(path))
    with open(path) as f:
        root_node = ast.parse(f.read())
        ast_utils.interlink_ast(root_node)
        ClassVisitor(path).visit(root_node)
        FunctionVisitor(path).visit(root_node)


def collect_standard_classes():
    def is_hidden(name):
        return name.startswith('_')

    import builtins
    for module_attr_name, module_attr in vars(builtins).items():
        if is_hidden(module_attr_name):
            continue
        if inspect.isclass(module_attr):
            class_name = module_attr.__qualname__
            class_bases = tuple(b.__qualname__ for b in module_attr.__bases__)
            attributes = [name for name in dir(module_attr) if not is_hidden(name)]
            cls_def = ClassDefinition(class_name, None, class_bases, attributes)
            _classes_index[class_name] = cls_def
            for attr in attributes:
                _class_attributes[attr].add(cls_def)


def suggest_classes(structural_type):
    base_classes = {attr: _class_attributes[attr] for attr in structural_type.attributes}
    if not base_classes:
        return set()
    suitable = functools.reduce(set.intersection, base_classes.values())
    return suitable


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

    collect_standard_classes()
    start_time = time.process_time()
    LOG.debug('Started inferring parameter types')
    for func in _functions_index.values():
        for param in func.parameters:
            structural_type = StructuralType(param.attributes)
            param.suggested_types = suggest_classes(structural_type)
    LOG.debug('Stopped inferring: %fs spent\n', time.process_time() - start_time)
    if LOG.isEnabledFor(logging.INFO):
        Stat.display(all_params=True)


def log_items(items, header, *args, level=logging.INFO):
    LOG.log(level, '{}'.format(header), *args)
    for item in items:
        LOG.log(level, '  %s', item)
    LOG.log(level, '')


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
