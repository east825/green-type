from __future__ import unicode_literals, print_function, division
import ast
import functools
import heapq
import importlib
import inspect
import logging
from collections import defaultdict
from contextlib import contextmanager
import operator
import os
import random
import sys
import textwrap

from . import ast_utils
from . import utils
from .utils import PY2


BUILTINS = '__builtin__' if PY2 else 'builtins'

LOG = logging.getLogger(__name__)

# TODO: invent something better than global mutable state
SRC_ROOTS = []
TEST_MODE = False


def path_to_module(path):
    path = os.path.abspath(path)
    roots = SRC_ROOTS + [p for p in sys.path if p not in ('', '.', os.getcwd())]
    for src_root in roots:
        if path.startswith(src_root):
            # TODO: check that on all way up to module correct packages with __init__ is used
            relative = os.path.relpath(path, src_root)
            dir_name, base_name = os.path.split(relative)
            if base_name == '__init__.py':
                prepared = dir_name
            else:
                prepared, _ = os.path.splitext(relative)
            return prepared.replace(os.path.sep, '.').strip('.')
    raise ValueError('Unresolved module: path={!r}'.format(path))


def module_to_path(module_name):
    rel_path = os.path.join(*module_name.split('.'))
    for src_root in SRC_ROOTS + sys.path:
        path = os.path.join(src_root, rel_path)
        package_path = os.path.join(path, '__init__.py')
        if os.path.isfile(package_path):
            return package_path
        module_path = path + '.py'
        if os.path.isfile(module_path):
            return os.path.abspath(module_path)
    raise ValueError('Unresolved module: name={!r}'.format(module_name))


def index_module_by_path(path, recursively=True):
    try:
        module_name = path_to_module(path)
    except ValueError as e:
        LOG.warning(e)
        return None
    loaded = Indexer.MODULE_INDEX.get(module_name)
    if loaded:
        return loaded
    return SourceModuleIndexer(path).run(recursively)


def index_module_by_name(name, recursively=True):
    loaded = Indexer.MODULE_INDEX.get(name)
    if loaded:
        return loaded
    try:
        path = module_to_path(name)
    except ValueError as e:
        LOG.warning(e)
        return None
    return SourceModuleIndexer(path).run(recursively)


def index_builtins():
    builtins = list(sys.builtin_module_names)
    builtins.append('_socket')
    if PY2:
        builtins.append('datetime')

    for module_name in builtins:
        ReflectiveModuleIndexer(module_name).run()


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
    def __init__(self, qname, node, path, imports):
        super(ModuleDefinition, self).__init__(qname, node)
        self.path = path
        # top-level imports
        self.imports = imports

    def __str__(self):
        return 'module {} at {!r}'.format(self.qname, self.path)


class Import(object):
    def __init__(self, imported_name, local_name, import_from, star_import=False):
        assert not (star_import and not import_from)
        assert not (local_name is None and not star_import)
        self.imported_name = imported_name
        self.local_name = local_name
        self.star_import = star_import
        self.import_from = import_from

    def imports_name(self, name):
        if self.star_import:
            return False
        return utils.qname_qualified_by(name, self.local_name)


class ClassDefinition(Definition):
    def __init__(self, qname, node, module, bases, attributes):
        super(ClassDefinition, self).__init__(qname, node)
        self.module = module
        self.bases = bases
        self.attributes = attributes

    def __str__(self):
        return 'class {}({})'.format(self.qname, ', '.join(self.bases))


class FunctionDefinition(Definition):
    def __init__(self, qname, node, module, parameters):
        super(FunctionDefinition, self).__init__(qname, node)
        self.module = module
        self.parameters = parameters

    def unbound_parameters(self):
        # outer_class = ast_utils.find_parent(self.node, ast.ClassDef, stop_cls=ast.FunctionDef, strict=True)
        # if outer_class is not None:
        if self.parameters and self.parameters[0].name == 'self':
            return self.parameters[1:]
        return self.parameters

    def __str__(self):
        return 'def {}({})'.format(self.qname, ', '.join(p.name for p in self.parameters))


class Parameter(object):
    def __init__(self, qname, attributes):
        self.qname = qname
        self.attributes = attributes
        self.suggested_types = set()
        self.used_as_argument = 0
        self.used_directly = 0
        self.used_as_operand = 0
        self.returned = 0

    @property
    def name(self):
        return utils.partition_any(self.qname, '#.', from_end=True)[1]

    def __str__(self):
        s = '{}::{}'.format(self.qname, StructuralType(self.attributes))
        if self.suggested_types:
            s = '{} ~ {}'.format(s, self.suggested_types)
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
            super(AttributesCollector, self).visit(node)


class SimpleAttributesCollector(AttributesCollector):
    """Collect only immediately accessed attributes for qualifier.

    No alias or scope analysis is used. Operators and other special methods
    are considered, hover subscriptions are.
    """

    def __init__(self, name, read_only=True):
        super(SimpleAttributesCollector, self).__init__()
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
            elif isinstance(node.ctx, ast.Store):
                self.attributes.add('__setitem__')
            elif isinstance(node.ctx, ast.Del):
                self.attributes.add('__delitem__')


class UsagesCollector(AttributesCollector):
    def __init__(self, name):
        super(UsagesCollector, self).__init__()
        self.name = name

    def collect(self, node):
        self.used_as_argument = 0
        self.used_as_operand = 0
        self.used_directly = 0
        self.returned = 0
        self.visit(node)

    def visit_Name(self, node):
        parent = ast_utils.node_parent(node)
        if not isinstance(parent, (ast.Attribute, ast.Subscript)):
            if node.id == self.name:
                self.used_directly += 1
                # keywords lhs is identifier (raw str) and lhs is value
                if isinstance(parent, (ast.keyword, ast.Call)):
                    self.used_as_argument += 1
                if isinstance(parent, ast.Return):
                    self.returned += 1
                if isinstance(parent, (ast.BinOp, ast.UnaryOp)):
                    self.used_as_operand += 1


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

    def register(self, definition):
        if isinstance(definition, ClassDefinition):
            self.register_class(definition)
        elif isinstance(definition, FunctionDefinition):
            self.register_function(definition)
        raise TypeError('Unknown definition: {}'.format(definition))

    def collect_class_attributes(self, class_def):
        return class_def.attributes


class SourceModuleIndexer(Indexer, ast.NodeVisitor):
    def __init__(self, path):
        super(SourceModuleIndexer, self).__init__()
        self.module_path = os.path.abspath(path)
        self.scopes_stack = []
        self.module_def = None
        self.depth = 0
        self.root = None

    def qualified_name(self, node):
        node_name = ast_utils.node_name(node)
        scope_owner = self.parent_scope()
        if scope_owner:
            return scope_owner.qname + '.' + node_name
        return node_name

    def run(self, recursively=True):
        if path_to_module(self.module_path) in Indexer.MODULE_INDEX:
            return

        LOG.debug('Indexing module %r', self.module_path)
        with open(self.module_path) as f:
            self.root = ast.parse(f.read(), self.module_path)
        ast_utils.interlink_ast(self.root)
        self.visit(self.root)
        if recursively and self.module_def:
            for imp in self.module_def.imports:
                if not imp.import_from or imp.star_import:
                    # for imports of form
                    # >>> for import foo.bar
                    # or
                    # >>> from foo.bar import *
                    # go straight to 'foo.bar'
                    index_module_by_name(imp.imported_name, recursively)
                else:
                    # in case of import of form
                    # >>> from foo.bar import baz [as quux]
                    # try to index both modules: foo.bar.baz and foo.bar
                    # the latter is needed if baz is top-level name in foo/bar/__init__.py
                    index_module_by_name(imp.imported_name, recursively)
                    index_module_by_name(utils.qname_tail(imp.imported_name), recursively)
        return self.module_def

    def visit(self, node):
        self.depth += 1
        try:
            super(SourceModuleIndexer, self).visit(node)
        finally:
            self.depth -= 1

    def parent_scope(self):
        if self.scopes_stack:
            return self.scopes_stack[-1]
        return None

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
                    imports.append(Import(alias.name, alias.asname or alias.name, False))
            elif isinstance(child, ast.ImportFrom):
                if child.level:
                    package_path = self.module_path
                    # correctly handle absolute/relative names, drives etc.
                    for _ in range(child.level):
                        package_path = os.path.dirname(package_path)
                    package = path_to_module(package_path)
                else:
                    package = ''
                if child.module and package:
                    target_module = package + '.' + child.module
                elif child.module:
                    target_module = child.module
                elif package:
                    target_module = package
                else:
                    raise Exception('Malformed ImportFrom statement: '
                                    'file={!r} module={}, level={}'.format(self.module_path,
                                                                           child.module,
                                                                           child.level))
                for alias in child.names:
                    if alias.name == '*':
                        imports.append(Import(target_module, None, True, True))
                    else:
                        imported_name = '{}.{}'.format(target_module, alias.name)
                        imports.append(
                            Import(imported_name, alias.asname or alias.name, True, False))
        module_def = ModuleDefinition(path_to_module(self.module_path), node, self.module_path,
                                      imports)
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
                    self_attributes = SimpleAttributesCollector('self', read_only=False).collect(
                        func_node)
                    self.attributes.update(self_attributes)

            def visit_Assign(self, assign_node):
                target = assign_node.targets[0]
                if isinstance(target, ast.Name):
                    self.attributes.add(target.id)

        class_attributes = ClassAttributeCollector().collect(node)
        class_def = ClassDefinition(class_name, node, self.module_def, bases_names,
                                    class_attributes)
        self.register_class(class_def)
        return class_def

    def function_discovered(self, node):
        func_name = self.qualified_name(node)
        args = node.args
        parent_scope = self.parent_scope()

        decorators = [ast_utils.attributes_chain_to_name(d) for d in node.decorator_list]
        if isinstance(parent_scope, ClassDefinition) and \
                not ('staticmethod' in decorators or 'classmethod' in decorators):
            declared_params = args.args[1:]
        else:
            declared_params = args.args

        if PY2:
            # exact order doesn't matter here
            declared_params += [args.vararg] + [args.kwarg]
        else:
            declared_params += [args.vararg] + args.kwonlyargs + [args.kwarg]

        parameters = []
        for arg in declared_params:
            # *args and **kwargs may be None
            if arg is None:
                continue
            if isinstance(arg, str):
                param_name = arg
            elif PY2:
                if isinstance(arg, ast.Name):
                    param_name = arg.id
                else:
                    LOG.warning('Function %s uses argument patterns. Skipped.', func_name)
            else:
                param_name = arg.arg
            attributes = SimpleAttributesCollector(param_name).collect(node.body)
            param_qname = func_name + '.' + param_name
            param = Parameter(param_qname, attributes)
            collector = UsagesCollector(param_name)
            collector.collect(node.body)
            param.used_as_argument = collector.used_as_argument
            param.used_as_operand = collector.used_as_operand
            param.used_directly = collector.used_directly
            param.returned = collector.returned
            parameters.append(param)

        func_def = FunctionDefinition(func_name, node, self.module_def, parameters)
        self.register_function(func_def)
        return func_def


class ReflectiveModuleIndexer(Indexer):
    def __init__(self, module_name):
        self.module_name = module_name

    def run(self):
        LOG.debug('Reflectively analyzing %r', self.module_name)

        def name(obj):
            return obj.__name__ if PY2 else obj.__qualname__

        module = importlib.import_module(self.module_name, None)
        module_def = ModuleDefinition(self.module_name, None, None, ())
        for module_attr_name, module_attr in vars(module).items():
            if inspect.isclass(module_attr):
                cls = module_attr
                class_name = self.module_name + '.' + name(cls)
                bases = tuple(name(b) for b in cls.__bases__)
                attributes = set(vars(cls))
                self.register_class(ClassDefinition(class_name, None, None, bases, attributes))
        self.register_module(module_def)


class Statistic(object):
    def __init__(self, total=True, prolific_params=True, param_types=True,
                 dump_functions=False, dump_classes=False, dump_params=False,
                 top_size=20, prefix='', dump_usages=False, random_inferred=True):
        self.show_total = total
        self.show_prolific_params = prolific_params
        self.show_param_types = param_types
        self.show_random_inferred = random_inferred
        self.dump_functions = dump_functions
        self.dump_classes = dump_classes
        self.dump_params = dump_params
        self.dump_usages = dump_usages
        self.top_size = top_size
        self.prefix = prefix

    @property
    def parameters(self):
        return list(Indexer.PARAMETERS_INDEX.values())

    @property
    def classes(self):
        return list(Indexer.CLASS_INDEX.values())

    @property
    def functions(self):
        return list(Indexer.FUNCTION_INDEX.values())

    def total_functions(self):
        return len(Indexer.FUNCTION_INDEX)

    def total_classes(self):
        return len(Indexer.CLASS_INDEX)

    def total_attributes(self):
        return len(Indexer.CLASS_ATTRIBUTE_INDEX)

    def total_parameters(self):
        return len(Indexer.PARAMETERS_INDEX)

    def _definitions_under_path(self, definitions, path):
        result = []
        for definition in definitions:
            if definition.module and definition.module.path.startswith(path):
                result.append(definition)
        return result

    def _filter_prefix(self, definitions):
        return (d for d in definitions if d.qname.startswith(self.prefix))

    def attributeless_params(self):
        return [p for p in Indexer.PARAMETERS_INDEX.values() if not p.attributes]

    def undefined_parameters(self):
        return [p for p in Indexer.PARAMETERS_INDEX.values() if
                p.attributes and not p.suggested_types]

    def inferred_parameters(self):
        return [p for p in Indexer.PARAMETERS_INDEX.values() if len(p.suggested_types) == 1]

    def scattered_parameters(self):
        return [p for p in Indexer.PARAMETERS_INDEX.values() if len(p.suggested_types) > 1]

    def top_parameters_with_most_attributes(self, n, exclude_self=True):
        if exclude_self:
            # params = itertools.chain.from_iterable(f.unbound_parameters() for f in _functions_index.values())
            params = [p for p in Indexer.PARAMETERS_INDEX.values() if p.name != 'self']
        else:
            params = Indexer.PARAMETERS_INDEX.values()
        return heapq.nlargest(n, params, key=lambda x: len(x.attributes))

    def top_parameters_with_scattered_types(self, n):
        return heapq.nlargest(n, self.scattered_parameters(), key=lambda x: len(x.suggested_types))

    def sample_parameters_with_unresolved_types(self, n):
        # [p for p in Indexer.PARAMETERS_INDEX.values() if p.attributes and not p.suggested_types][:n]
        result = []
        for param in Indexer.PARAMETERS_INDEX.values():
            if param.attributes and not param.suggested_types:
                result.append(param)
            if len(result) > n:
                break
        return result

    def sample_parameters_not_used_anywhere(self, n):
        result = []
        for param in Indexer.PARAMETERS_INDEX.values():
            if not param.attributes and not param.used_directly:
                result.append(param)
            if len(result) > n:
                break
        return result

    def format(self):
        formatted = ''
        if self.show_total:
            formatted += 'Total indexed: {} classes with {} attributes, ' \
                         '{} functions with {} parameters'.format(self.total_classes(),
                                                                  self.total_attributes(),
                                                                  self.total_functions(),
                                                                  self.total_parameters())
        if self.show_prolific_params:
            prolific_params = self.top_parameters_with_most_attributes(self.top_size)
            formatted += self._format_list(
                header='Most frequently accessed parameters (top {}):'.format(self.top_size),
                items=prolific_params,
                prefix_func=lambda x: '{:3} attributes'.format(len(x.attributes))
            )

        if self.show_param_types:
            total_params = len(Indexer.PARAMETERS_INDEX)
            attributeless_params = self.attributeless_params()
            total_attributeless = len(attributeless_params)
            total_undefined = len(self.undefined_parameters())
            total_inferred = len(self.inferred_parameters())
            total_scattered = len(self.scattered_parameters())
            formatted += textwrap.dedent("""
            Parameters statistic:
              {} ({:.2%}) parameters have no attributes (types cannot be inferred):
              However, of them:
                - {:.2%} used directly somehow (no attribute access or subscripts)
                - {:.2%} passed as arguments to other function
                - {:.2%} used as operands in arithmetic or logical expressions
                - {:.2%} returned from function
              {} ({:.2%}) parameters have some parameters, but no type inferred,
              {} ({:.2%}) parameters have exactly one type inferred,
              {} ({:.2%}) parameters have more then one inferred type (scattered types)
            """.format(
                total_attributeless, (total_attributeless / total_params),
                sum(p.used_directly > 0 for p in attributeless_params) / total_attributeless,
                sum(p.used_as_argument > 0 for p in attributeless_params) / total_attributeless,
                sum(p.used_as_operand > 0 for p in attributeless_params) / total_attributeless,
                sum(p.returned > 0 for p in attributeless_params) / total_attributeless,
                total_undefined, (total_undefined / total_params),
                total_inferred, (total_inferred / total_params),
                total_scattered, (total_scattered / total_params)))

            formatted += self._format_list(
                header='Parameters with scattered type (top {}):'.format(self.top_size),
                items=self.top_parameters_with_scattered_types(self.top_size),
                prefix_func=lambda x: '{:3} types'.format(len(x.suggested_types))
            )

            formatted += self._format_list(
                header='Parameters with accessed attributes, '
                       'but with no suggested classes (first {})'.format(self.top_size),
                items=self.sample_parameters_with_unresolved_types(self.top_size)
            )

            formatted += self._format_list(
                header='Parameters that have no attributes and not used directly '
                       'elsewhere (first {})'.format(self.top_size),
                items=self.sample_parameters_not_used_anywhere(self.top_size)
            )

        if self.show_random_inferred:
            params = list(self._filter_prefix(self.inferred_parameters()))
            quantity = min(self.top_size, len(params))
            formatted += self._format_list(
                header='Parameters with definitively inferred types '
                       '(random {}, total {})'.format(quantity, len(params)),
                items=random.sample(params, quantity)
            )

        if self.dump_classes:
            classes = self._filter_prefix(Indexer.CLASS_INDEX.values())
            formatted += self._format_list(header='Classes:', items=classes)
        if self.dump_functions:
            functions = self._filter_prefix(Indexer.FUNCTION_INDEX.values())
            formatted += self._format_list(header='Functions:', items=functions)
        if self.dump_params:
            parameters = self._filter_prefix(Indexer.PARAMETERS_INDEX.values())
            chunks = []
            for param in sorted(parameters, key=operator.attrgetter('qname')):
                chunks.append(textwrap.dedent("""\
                Parameter {}:
                - used directly: {:d} times
                - passed to other function: {:d} times
                - used in arithmetic and logical expressions {:d} times
                - returned: {:d} times
                """.format(param,
                           param.used_directly,
                           param.used_as_argument,
                           param.used_as_operand,
                           param.returned)))
            formatted += self._format_list(header='Parameters', items=chunks)
        return formatted

    def __str__(self):
        return self.format()

    def __repr__(self):
        preferences = ', '.join('{}={}'.format(k, v) for k, v in vars(self).items())
        return 'Statistic({})'.format(preferences)

    def _format_list(self, items, header=None, prefix_func=None, indent='  '):
        formatted = '\n'
        if header is not None:
            formatted += '{}\n'.format(header)
        if not items:
            formatted += indent + 'none'
        else:
            blocks = []
            for item in items:
                item_text = str(item)
                if prefix_func is not None:
                    prefix = '{}{} : '.format(indent, prefix_func(item))
                    lines = item_text.splitlines()
                    first_line, remaining_lines = lines[0], lines[1:]
                    block = '{}{}'.format(prefix, first_line)
                    if remaining_lines:
                        indented_tail = utils.indent('\n'.join(remaining_lines), ' ' * len(prefix))
                        blocks.append('{}\n{}'.format(block, indented_tail))
                    else:
                        blocks.append(block)
                else:
                    blocks.append(utils.indent(item_text, indent))
            formatted += '\n'.join(blocks)
        return formatted + '\n'


@utils.memo
def resolve_name(name, module, type):
    """Resolve name using indexes and following import if it's necessary."""

    def check_loaded(qname, module=None):
        if type is ClassDefinition:
            definition = Indexer.CLASS_INDEX.get(qname)
        else:
            definition = Indexer.FUNCTION_INDEX.get(qname)
        return definition

    # already properly qualified name or built-in
    df = check_loaded(name) or check_loaded(BUILTINS + '.' + name)
    if df:
        return df

    # not built-in
    if module:
        # name defined in the same module
        df = check_loaded('{}.{}'.format(module.qname, name), module)
        if df:
            return df
        # name is imported
        for imp in module.imports:
            if imp.imports_name(name):
                qname = utils.qname_merge(imp.local_name, name)
                # TODO: more robust qualified name handling
                qname = qname.replace(imp.local_name, imp.imported_name, 1)
                # Case 1:
                # >>> import some.module as alias
                # index some.module, then check some.module.Base
                # Case 2:
                # >>> from some.module import Base as alias
                # index some.module, then check some.module.Base
                # if not found index some.module.Base, then check some.module.Base again
                df = check_loaded(qname, module)
                if df:
                    return df

                if not imp.import_from:
                    module_loaded = index_module_by_name(imp.imported_name)
                    if module_loaded:
                        # drop local name (alias) for imports like
                        # import module as alias
                        # print(alias.MyClass.InnerClass())
                        top_level_name = utils.qname_drop(name, imp.local_name)
                        df = resolve_name(top_level_name, module_loaded, type)
                        if df:
                            return df
                        LOG.info('Module %r referenced as "import %s" in %r loaded '
                                 'successfully, but class %r not found',
                                 imp.imported_name, imp.imported_name, module.path, qname)
                else:
                    # first, interpret import like 'from module import Name'
                    module_name = utils.qname_tail(imp.imported_name)
                    module_loaded = index_module_by_name(module_name)
                    if module_loaded:
                        top_level_name = utils.qname_drop(qname, module_name)
                        df = resolve_name(top_level_name, module_loaded, type)
                        if df:
                            return df
                    # then, as 'from package import module'
                    module_loaded = index_module_by_name(imp.imported_name)
                    if module_loaded:
                        top_level_name = utils.qname_drop(name, imp.local_name)
                        df = resolve_name(qname, top_level_name, type)
                        if df:
                            return df
                        LOG.info('Module %r referenced as "from %s import %s" in %r loaded '
                                 'successfully, but class %r not found',
                                 imp.imported_name, utils.qname_tail(imp.imported_name),
                                 utils.qname_head(imp.imported_name), module.path,
                                 qname)
            elif imp.star_import:
                module_loaded = index_module_by_name(imp.imported_name)
                if module_loaded:
                    # no aliased allowed with 'from module import *' so we check directly
                    # for name searched in the first place
                    df = resolve_name(name, module_loaded, type)
                    if df:
                        return df

    LOG.warning('Cannot resolve name %r in module %r', name, module or '<undefined>')


@utils.memo
def resolve_bases(class_def):
    LOG.debug('Resolving bases for %r', class_def.qname)
    bases = set()

    for name in class_def.bases:
        # fully qualified name or built-in
        base_def = resolve_name(name, class_def.module, ClassDefinition)
        if base_def:
            bases.add(base_def)
            bases.update(resolve_bases(base_def))
        else:
            LOG.warning('Base class %r of %r not found', name, class_def.qname)
    return bases


def suggest_classes_by_attributes(accessed_attrs):
    def unite(sets):
        return functools.reduce(set.union, sets, set())

    def intersect(sets):
        if not sets:
            return {}
        return functools.reduce(set.intersection, sets)

    class_pool = {attr: Indexer.CLASS_ATTRIBUTE_INDEX[attr] for attr in accessed_attrs}
    if not class_pool:
        return set()
    with_any_attribute = unite(class_pool.values())

    # with_all_attributes = intersect(class_pool.values())
    # suitable_classes = set(with_all_attributes)
    # for class_def in with_any_attribute - with_all_attributes:
    # bases = resolve_bases(class_def)
    # all_attrs = unite(b.attributes for b in bases) | class_def.attributes
    # if accessed_attrs <= all_attrs:
    # suitable_classes.add(class_def)

    # More fair algorithm because it considers newly discovered bases classes as well
    suitable_classes = set()
    candidates = set(with_any_attribute)
    checked = set()
    while candidates:
        candidate = candidates.pop()
        checked.add(candidate)
        bases = resolve_bases(candidate)
        all_attrs = unite(b.attributes for b in bases) | candidate.attributes
        if accessed_attrs <= all_attrs:
            suitable_classes.add(candidate)
        for base in bases:
            if base in candidates or base in checked:
                continue
            if any(attr in base.attributes for attr in accessed_attrs):
                candidates.add(base)

    # remove subclasses if their superclasses is suitable also
    for cls in suitable_classes.copy():
        if any(base in suitable_classes for base in resolve_bases(cls)):
            suitable_classes.remove(cls)

    return suitable_classes