import ast
import importlib
import inspect
import logging
from collections import defaultdict
from contextlib import contextmanager

from . import ast_utils
from . import utils
import itertools
import os
import sys

LOG = logging.getLogger(__name__)

SRC_ROOTS = []

def path2qname(path):
    path = os.path.abspath(path)
    for src_root in SRC_ROOTS + sys.path:
        if path.startswith(src_root):
            relative = os.path.relpath(path, src_root)
            dir_name, base_name = os.path.split(relative)
            if base_name == '__init__.py':
                prepared = dir_name
            else:
                prepared, _ =  os.path.splitext(relative)
            return prepared.replace(os.path.sep, '.').strip('.')
    raise ValueError('Unresolved module {!r}'.format(path))


class Definition(object):
    def __init__(self, qname, node):
        self.qname = qname
        self.node = node

    @property
    def name(self):
        return utils.partition_any(self.qname, '#.', from_end=True)[1]

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


class ModuleDefinition(Definition):
    def __init__(self, qname, node, path, top_level_imports):
        super().__init__(qname, node)
        self.path = path
        self.imports = top_level_imports

    def __str__(self):
        return 'module {} at {!r}'.format(self.qname, self.path)


class Import(object):
    def __init__(self, imported_name, local_name=None, star=False):
        self.imported_name = imported_name
        self.local_name = local_name if local_name else imported_name
        self.star = star

    def imports_name(self, name, star_imports=False):
        if self.star and star_imports:
            return True
        return name.startswith(self.local_name)


class ClassDefinition(Definition):
    def __init__(self, qname, node, module, bases, attributes):
        super().__init__(qname, node)
        self.module = module
        self.bases = bases
        self.attributes = attributes

    def __str__(self):
        return 'class {}({})'.format(self.qname, ', '.join(self.bases))


class FunctionDefinition(Definition):
    def __init__(self, qname, node, module, parameters):
        super().__init__(qname, node)
        self.module = module
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


class Parameter(object):
    def __init__(self, qname, attributes):
        self.qname = qname
        self.attributes = attributes
        self.suggested_types = set()

    @property
    def name(self):
        return utils.partition_any(self.qname, '#.', from_end=True)[1]

    def __str__(self):
        s = '{}::{}'.format(self.qname, StructuralType(self.attributes))
        if self.suggested_types:
            return '{} ~ {}'.format(s, self.suggested_types)
        return s


class StructuralType(object):
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


class Indexer(object):
    CLASS_INDEX = {}
    CLASS_ATTRIBUTE_INDEX = defaultdict(set)
    FUNCTION_INDEX = {}
    PARAMETERS_INDEX = {}
    MODULE_INDEX = {}

    def run(self, *args, **kwargs):
        raise NotImplementedError()

    def register_class(self, class_def):
        Indexer.CLASS_INDEX[class_def.qname] = class_def
        for attr in self.collect_class_attributes(class_def):
            Indexer.CLASS_ATTRIBUTE_INDEX[attr].add(class_def)

    def register_function(self, func_def):
        Indexer.FUNCTION_INDEX[func_def.qname] = func_def
        for param in func_def.parameters:
            Indexer.PARAMETERS_INDEX[param.qname] = param

    def register_module(self, module_def):
        Indexer.MODULE_INDEX[module_def.qname] = module_def

    def collect_class_attributes(self, class_def):
        return class_def.attributes


class SourceModuleIndexer(Indexer, ast.NodeVisitor):
    def __init__(self, path):
        super().__init__()
        self.module_path = path
        self.scopes_stack = []
        self.depth = 0
        self.root = None

    def qualified_name(self, node):
        node_name = ast_utils.node_name(node)
        if self.scopes_stack:
            return self.scopes_stack[-1].qname + '.' + node_name
        return node_name

    def run(self):
        LOG.debug('Analyzing module %r', self.module_path)
        with open(self.module_path) as f:
            self.root = ast.parse(f.read(), self.module_path)
        ast_utils.interlink_ast(self.root)
        self.visit(self.root)

    def visit(self, node):
        self.depth += 1
        try:
            super().visit(node)
        finally:
            self.depth -= 1

    @contextmanager
    def scope_owner(self, definition):
        self.scopes_stack.append(definition)
        try:
            yield
        finally:
            self.scopes_stack.pop()

    def visit_Module(self, node):
        self.module_def = module_def = self.module_discovered(node)
        with self.scope_owner(module_def):
            self.generic_visit(node)

    def visit_ClassDef(self, node):
        class_def = self.class_discovered(node)
        with self.scope_owner(class_def):
            self.generic_visit(node)

    def visit_FunctionDef(self, node):
        func_def = self.function_discovered(node)
        with self.scope_owner(func_def):
            self.generic_visit(node)

    def module_discovered(self, node):
        imports = []
        # inspect only top-level imports
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.Import):
                for alias in child.names:
                    imports.append(Import(alias.name, alias.asname))
            elif isinstance(child, ast.ImportFrom):
                if child.level:
                    path_components = self.module_path.split(os.path.sep)
                    package_path = os.path.join(path_components[:-child.level])
                    package = path2qname(package_path)
                else:
                    package = ''
                if child.module and package:
                    target_module = package + '.' + child.module
                elif child.module:
                    target_module = child.module
                elif package:
                    target_module = package
                else:
                    raise Exception(
                        'Malformed ImportFrom statement: file={!r} module={}, level={}'.format(
                            self.module_path, child.module, child.level))
                for alias in child.names:
                    name = target_module + '.' + alias.name
                    imports.append(Import(name, alias.asname))
        module_def = ModuleDefinition(path2qname(self.module_path), node,  self.module_path, imports)
        self.register_module(module_def)
        return module_def

    def class_discovered(self, node):
        class_name = self.qualified_name(node)
        bases_names = []
        for expr in node.bases:
            base_name = ast_utils.attributes_chain_to_name(expr)
            if base_name is None:
                LOG.warning('Class %s in module %s uses computed bases. Not supported.',
                            class_name, self.module_def.path)
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
        class_def = ClassDefinition(class_name, node, self.module_def, bases_names, class_attributes)
        self.register_class(class_def)
        return class_def

    def function_discovered(self, node):
        func_name = self.qualified_name(node)
        parameters = []
        for arg in itertools.chain(node.args.args, [node.args.vararg], node.args.kwonlyargs, [node.args.kwarg]):
            # *args and **kwargs may be None
            if arg is None:
                continue
            param_name = arg if isinstance(arg, str) else arg.arg
            attributes = SimpleAttributesCollector(param_name).collect(node)
            param_qname = func_name + '.' + param_name
            parameters.append(Parameter(param_qname, attributes))

        func_def = FunctionDefinition(self.module_def.path, func_name, node, parameters)
        self.register_function(func_def)
        return func_def

class ReflectiveModuleIndexer(Indexer):
    def __init__(self, module_name):
        self.module_name = module_name

    def run(self):
        LOG.debug('Reflectively analyzing %r', self.module_name)
        def is_hidden(name):
            return name.startswith('_')

        module = importlib.import_module(self.module_name, None)
        for module_attr_name, module_attr in vars(module).items():
            if is_hidden(module_attr_name):
                continue
            if inspect.isclass(module_attr):
                class_name = module_attr.__qualname__
                bases = tuple(b.__qualname__ for b in module_attr.__bases__)
                attributes = [name for name in dir(module_attr) if not is_hidden(name)]
                self.register_class(ClassDefinition(class_name, None, None, bases, attributes))