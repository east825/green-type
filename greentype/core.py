from __future__ import unicode_literals, print_function, division
import ast
import functools
import heapq
import importlib
import inspect
import json
import logging
from contextlib import contextmanager
import operator
import os
import random
import sys
import textwrap

from . import ast_utils
from . import utils
from .utils import PY2, memoized


BUILTINS = '__builtin__' if PY2 else 'builtins'

LOG = logging.getLogger(__name__)

from collections import defaultdict

# TODO: it's better to be Trie, views better to be immutable
class Index(defaultdict):
    def items(self, key_filter=None):
        return ((k, self[k]) for k in self.keys(key_filter))

    def values(self, key_filter=None):
        return (self[k] for k in self.keys(key_filter))

    def keys(self, key_filter=None):
        all_keys = super(Index, self).keys()
        if key_filter is None:
            return all_keys
        return (k for k in all_keys if key_filter(k))


class StatisticUnit(object):
    __slots__ = ('_min', '_max', '_items', '_counter', '_data')

    def __init__(self):
        self._min = None
        self._max = None
        self._data = None
        self._items = None
        self._counter = None

    def update(self, collection):
        if self._items is None:
            self._items = set()
        self._items.update(collection)

    def add(self, *items):
        if self._items is None:
            self._items = set()
        self._items.add(*items)

    def inc(self, value=1):
        if self._counter is None:
            self._counter = 0
        self._counter += value

    def set_max(self, value, data=None):
        if self._max is None:
            self._max = value
        else:
            self._max = max(self._max, value)
        if self._max == value:
            self._data = data

    def set_min(self, value, data=None):
        if self._min is None:
            self._min = value
        else:
            self._min = min(self._min, value)
        if self._min == value:
            self._data = data

    def __iadd__(self, other):
        self.inc(other)

    def as_dict(self, skip_none=True):
        d = {}
        for name in self.__slots__:
            attr = getattr(self, name)
            if attr is None and skip_none:
                continue
            d[name.strip('_')] = attr
        return d

    def value(self):
        for name in self.__slots__:
            attr = getattr(self, name)
            if attr is not None:
                return attr


class Config(dict):
    """Configuration similar to the one used in Flask."""

    __defaults = {
        'FOLLOW_IMPORTS': True,
        'BUILTINS': sys.builtin_module_names + ('_socket', 'datetime'),

        'TARGET_NAME': None,
        'TARGET_PATH': None,

        'PROJECT_ROOT': None,
        'PROJECT_NAME': None,
        'SOURCE_ROOTS': None,

        'VERBOSE': False,
        'ANALYZE_BUILTINS': True
    }

    def __init__(self, *args, **kwargs):
        super(Config, self).__init__(self.__defaults)
        self.merge_with(dict(*args, **kwargs))

    def merge_with(self, other, override=True):
        for k, v in other.items():
            if k not in self:
                raise ValueError('Unrecognized config parameter {}'.format(k))
            # merge only lists for now
            elif isinstance(self[k], list) and isinstance(v, list):
                self[k] = self[k] + v
            elif self[k] is None or override:
                self[k] = v
            elif self[k] == v:
                pass
            else:
                raise ValueError('Cannot merge {!r} with {!r}'.format(self, other))

    def update_from_object(self, obj):
        d = {}
        for name in dir(obj):
            # if name in self.__defaults:
            if name.isupper():
                d[name] = getattr(obj, name)
        self.merge_with(d)


class GreenTypeAnalyzer(object):
    def __init__(self, target_path):
        self.indexes = {
            'MODULE_INDEX': Index(None),
            'CLASS_INDEX': Index(None),
            'FUNCTION_INDEX': Index(None),
            'PARAMETER_INDEX': Index(None),
            'CLASS_ATTRIBUTE_INDEX': Index(set)
        }

        self.config = Config()
        self.config['TARGET_PATH'] = target_path
        if os.path.isfile(target_path):
            project_root = os.path.dirname(target_path)
        elif os.path.isdir(target_path):
            project_root = target_path
        else:
            raise ValueError('Unrecognized target {!r}. '
                             'Should be either file or directory.'.format(target_path))
        self.config['PROJECT_ROOT'] = project_root
        self.config['PROJECT_NAME'] = os.path.basename(target_path)
        # if not source_roots:
        # source_roots = [project_root]
        # else:
        # source_roots = list(source_roots)
        # source_roots.insert(0, project_root)
        self.config['SOURCE_ROOTS'] = [project_root]
        self.statistics = defaultdict(StatisticUnit)


    @property
    def statistics_report(self):
        return StatisticsReport(self)

    @property
    def target_path(self):
        return self.config['TARGET_PATH']

    @property
    def project_name(self):
        return self.config['PROJECT_NAME']

    @property
    def project_root(self):
        return self.config['PROJECT_ROOT']

    @property
    def source_roots(self):
        return self.config['SOURCE_ROOTS']

    def _filter_root(self, definitions):
        return [d for d in definitions
                if d.module and d.module.path.startswith(self.project_root)]

    @property
    def project_modules(self):
        return self._filter_root(self.indexes['MODULE_INDEX'].values())

    @property
    def project_classes(self):
        return self._filter_root(self.indexes['CLASS_INDEX'].values())

    @property
    def project_functions(self):
        return self._filter_root(self.indexes['FUNCTION_INDEX'].values())

    @property
    def project_parameters(self):
        return self._filter_root(self.indexes['PARAMETER_INDEX'].values())

    def invalidate_indexes(self):
        for index in self.indexes.values():
            index.clear()

    def index_module(self, path=None, name=None):
        if name is None and path is None:
            raise ValueError('Either module name or module path should be given')

        if path is not None:
            try:
                name = self.path_to_module_name(path)
            except ValueError as e:
                LOG.warning(e)
                return None
            loaded = self.indexes['MODULE_INDEX'].get(name)
            if loaded:
                return loaded
            module_indexed = SourceModuleIndexer(self, path).run()
        else:
            loaded = self.indexes['MODULE_INDEX'].get(name)
            if loaded:
                return loaded
            try:
                path = self.module_name_to_path(name)
            except ValueError as e:
                LOG.warning(e)
                return None
            module_indexed = SourceModuleIndexer(self, path).run()

        if self.config['FOLLOW_IMPORTS']:
            for imp in module_indexed.imports:
                if not imp.import_from or imp.star_import:
                    # for imports of form
                    # >>> for import foo.bar
                    # or
                    # >>> from foo.bar import *
                    # go straight to 'foo.bar'
                    self.index_module(name=imp.imported_name)
                else:
                    # in case of import of form
                    # >>> from foo.bar import baz [as quux]
                    # try to index both modules: foo.bar.baz and foo.bar
                    # the latter is needed if baz is top-level name in foo/bar/__init__.py
                    self.index_module(name=imp.imported_name)
                    self.index_module(name=utils.qname_tail(imp.imported_name))
        return module_indexed

    def path_to_module_name(self, path):
        path = os.path.abspath(path)
        roots = self.source_roots + [p for p in sys.path if p not in ('', '.', os.getcwd())]
        for src_root in roots:
            if path.startswith(src_root):
                # check that on all way up to module correct packages with __init__ exist

                in_proper_package = True
                # package_path = os.path.dirname(path)
                # while package_path != src_root:
                # if not os.path.exists(os.path.join(package_path, '__init__.py')):
                # in_proper_package = False
                # break
                # package_path = os.path.dirname(package_path)

                relative = os.path.relpath(path, src_root)
                package_path = src_root
                for comp in relative.split(os.path.sep)[:-1]:
                    package_path = os.path.join(package_path, comp)
                    if not os.path.exists(os.path.join(package_path, '__init__.py')):
                        in_proper_package = False
                        break

                if not in_proper_package:
                    continue

                dir_name, base_name = os.path.split(relative)
                if base_name == '__init__.py':
                    prepared = dir_name
                else:
                    prepared, _ = os.path.splitext(relative)
                return prepared.replace(os.path.sep, '.').strip('.')
        raise ValueError('Unresolved module: path={!r}'.format(path))


    def module_name_to_path(self, module_name):
        rel_path = os.path.join(*module_name.split('.'))
        for src_root in self.source_roots + sys.path:
            path = os.path.join(src_root, rel_path)
            package_path = os.path.join(path, '__init__.py')
            if os.path.isfile(package_path):
                return package_path
            module_path = path + '.py'
            if os.path.isfile(module_path):
                return os.path.abspath(module_path)
        raise ValueError('Unresolved module: name={!r}'.format(module_name))


    def index_builtins(self):
        def object_name(obj):
            return obj.__name__ if PY2 else obj.__qualname__

        for module_name in self.config['BUILTINS']:
            LOG.debug('Reflectively analyzing %r', module_name)

            module = importlib.import_module(module_name, None)
            for module_attr_module_name, module_attr in vars(module).items():
                if inspect.isclass(module_attr):
                    cls = module_attr
                    class_name = module_name + '.' + object_name(cls)
                    bases = tuple(object_name(b) for b in cls.__bases__)
                    attributes = set(vars(cls))
                    class_def = ClassDef(class_name, None, None, bases, attributes)
                    self.indexes['CLASS_INDEX'][class_name] = class_def
                    for attr in attributes:
                        self.indexes['CLASS_ATTRIBUTE_INDEX'][attr].add(class_def)

    @memoized
    def resolve_name(self, name, module, type='class'):
        """Resolve name using indexes and following import if it's necessary."""

        if type == 'class':
            index = self.indexes['CLASS_INDEX']
        elif type == 'function':
            index = self.indexes['FUNCTION_INDEX']
        elif type == 'module':
            index = self.indexes['MODULE_INDEX']
        else:
            raise ValueError('Unknown definition type. Should be one of: class, function, module')

        def check_loaded(qname):
            if qname in index:
                return index[qname]

        # already properly qualified name or built-in
        df = check_loaded(name) or check_loaded(BUILTINS + '.' + name)
        if df:
            return df

        # not built-in
        if module:
            # name defined in the same module
            df = check_loaded('{}.{}'.format(module.qname, name))
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
                    df = check_loaded(qname)
                    if df:
                        return df

                    if not imp.import_from:
                        module_loaded = self.index_module(name=imp.imported_name)
                        if module_loaded:
                            # drop local name (alias) for imports like
                            # import module as alias
                            # print(alias.MyClass.InnerClass())
                            top_level_name = utils.qname_drop(name, imp.local_name)
                            df = self.resolve_name(top_level_name, module_loaded, type)
                            if df:
                                return df
                            LOG.info('Module %r referenced as "import %s" in %r loaded '
                                     'successfully, but class %r not found',
                                     imp.imported_name, imp.imported_name, module.path, qname)
                    else:
                        # first, interpret import like 'from module import Name'
                        module_name = utils.qname_tail(imp.imported_name)
                        module_loaded = self.index_module(name=module_name)
                        if module_loaded:
                            top_level_name = utils.qname_drop(qname, module_name)
                            df = self.resolve_name(top_level_name, module_loaded, type)
                            if df:
                                return df
                        # then, as 'from package import module'
                        module_loaded = self.index_module(name=imp.imported_name)
                        if module_loaded:
                            top_level_name = utils.qname_drop(name, imp.local_name)
                            df = self.resolve_name(top_level_name, module_loaded, type)
                            if df:
                                return df
                            LOG.info('Module %r referenced as "from %s import %s" in %r loaded '
                                     'successfully, but class %r not found',
                                     imp.imported_name, utils.qname_tail(imp.imported_name),
                                     utils.qname_head(imp.imported_name), module.path,
                                     qname)
                elif imp.star_import:
                    module_loaded = self.index_module(name=imp.imported_name)
                    if module_loaded:
                        # no aliased allowed with 'from module import *' so we check directly
                        # for name searched in the first place
                        df = self.resolve_name(name, module_loaded, type)
                        if df:
                            return df

        LOG.warning('Cannot resolve name %r in module %r', name, module or '<undefined>')

    @memoized
    def _resolve_bases(self, class_def):
        LOG.debug('Resolving bases for %r', class_def.qname)
        bases = set()

        for name in class_def.bases:
            # fully qualified name or built-in
            base_def = self.resolve_name(name, class_def.module, 'class')
            if base_def:
                bases.add(base_def)
                bases.update(self._resolve_bases(base_def))
            else:
                LOG.warning('Base class %r of %r not found', name, class_def.qname)
        return bases

    def infer_parameter_types(self):
        for param in self.project_parameters:
            param.suggested_types = self.suggest_classes(param.attributes)


    def suggest_classes(self, accessed_attrs):
        def unite(sets):
            return functools.reduce(set.union, sets, set())

        def intersect(sets):
            if not sets:
                return {}
            return functools.reduce(set.intersection, sets)

        class_pool = {attr: self.indexes['CLASS_ATTRIBUTE_INDEX'][attr] for attr in accessed_attrs}
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
            bases = self._resolve_bases(candidate)

            # register number of base classes for statistics
            num_bases = len(bases)
            self.statistics['max_bases'].set_max(num_bases, candidate.qname)

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
            if any(base in suitable_classes for base in self._resolve_bases(cls)):
                suitable_classes.remove(cls)

        return suitable_classes


class Definition(object):
    def __init__(self, qname, node, module):
        self.qname = qname
        self.node = node
        self.module = module

    @property
    def name(self):
        _, _, head = self.qname.rpartition('.')
        return head

    @property
    def physical(self):
        return self.module is not None and self.node is not None

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


class ModuleDef(Definition):
    def __init__(self, qname, node, path, imports):
        super(ModuleDef, self).__init__(qname, node, self)
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


class ClassDef(Definition):
    def __init__(self, qname, node, module, bases, attributes):
        super(ClassDef, self).__init__(qname, node, module)
        self.bases = bases
        self.attributes = attributes

    def __str__(self):
        return 'class {}({})'.format(self.qname, ', '.join(self.bases))


class FunctionDef(Definition):
    def __init__(self, qname, node, module, parameters):
        super(FunctionDef, self).__init__(qname, node, module)
        self.parameters = parameters

    def unbound_parameters(self):
        # outer_class = ast_utils.find_parent(self.node, ast.ClassDef, stop_cls=ast.FunctionDef, strict=True)
        # if outer_class is not None:
        if self.parameters and self.parameters[0].name == 'self':
            return self.parameters[1:]
        return self.parameters

    def __str__(self):
        return 'def {}({})'.format(self.qname, ', '.join(p.name for p in self.parameters))


class ParameterDef(Definition):
    def __init__(self, qname, attributes, node, module):
        super(ParameterDef, self).__init__(qname, node, module)
        self.qname = qname
        self.attributes = attributes
        self.suggested_types = set()
        self.used_as_argument = 0
        self.used_directly = 0
        self.used_as_operand = 0
        self.returned = 0

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


class SourceModuleIndexer(ast.NodeVisitor):
    def __init__(self, analyzer, path):
        self.analyzer = analyzer
        self.indexes = analyzer.indexes
        self.module_path = os.path.abspath(path)
        self.scopes_stack = []
        self.module_def = None
        self.depth = 0
        self.root = None

    def register_class(self, class_def):
        self.indexes['CLASS_INDEX'][class_def.qname] = class_def
        for attr in self.collect_class_attributes(class_def):
            self.indexes['CLASS_ATTRIBUTE_INDEX'][attr].add(class_def)

    def register_function(self, func_def):
        self.indexes['FUNCTION_INDEX'][func_def.qname] = func_def
        for param_def in func_def.parameters:
            self.indexes['PARAMETER_INDEX'][param_def.qname] = param_def

    def register_module(self, module_def):
        self.indexes['MODULE_INDEX'][module_def.qname] = module_def

    def register(self, definition):
        if isinstance(definition, ClassDef):
            self.register_class(definition)
        elif isinstance(definition, FunctionDef):
            self.register_function(definition)
        raise TypeError('Unknown definition: {}'.format(definition))

    def collect_class_attributes(self, class_def):
        return class_def.attributes

    def qualified_name(self, node):
        node_name = ast_utils.node_name(node)
        scope_owner = self.parent_scope()
        if scope_owner:
            return scope_owner.qname + '.' + node_name
        return node_name

    def run(self):
        LOG.debug('Indexing module %r', self.module_path)
        with open(self.module_path) as f:
            self.root = ast.parse(f.read(), self.module_path)
        ast_utils.interlink_ast(self.root)
        self.visit(self.root)
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
                    package = self.analyzer.path_to_module_name(package_path)
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
        module_name = self.analyzer.path_to_module_name(self.module_path)
        module_def = ModuleDef(module_name, node, self.module_path, imports)
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
        class_def = ClassDef(class_name, node, self.module_def, bases_names, class_attributes)
        self.register_class(class_def)
        return class_def

    def function_discovered(self, node):
        func_name = self.qualified_name(node)
        args = node.args
        parent_scope = self.parent_scope()

        decorators = [ast_utils.attributes_chain_to_name(d) for d in node.decorator_list]
        if isinstance(parent_scope, ClassDef) and \
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
                    continue
            else:
                param_name = arg.arg
            attributes = SimpleAttributesCollector(param_name).collect(node.body)
            param_qname = func_name + '.' + param_name
            param = ParameterDef(param_qname, attributes, None, self.module_def)
            collector = UsagesCollector(param_name)
            collector.collect(node.body)
            param.used_as_argument = collector.used_as_argument
            param.used_as_operand = collector.used_as_operand
            param.used_directly = collector.used_directly
            param.returned = collector.returned
            parameters.append(param)

        func_def = FunctionDef(func_name, node, self.module_def, parameters)
        self.register_function(func_def)
        return func_def


class StatisticsReport(object):
    def __init__(self, analyzer):
        self.analyzer = analyzer
        self.show_total = True
        self.show_prolific_params = True
        self.show_param_types = True
        self.show_random_inferred = True
        self.dump_functions = False
        self.dump_classes = False
        self.dump_params = True
        self.dump_usages = False
        self.top_size = 20
        self.prefix = analyzer.config['TARGET_NAME'] or ''

        self.modules = list(analyzer.indexes['MODULE_INDEX'].values())
        self.classes = list(analyzer.indexes['CLASS_INDEX'].values())
        self.functions = list(analyzer.indexes['FUNCTION_INDEX'].values())
        self.parameters = list(analyzer.indexes['PARAMETER_INDEX'].values())

        self.project_modules = list(self.analyzer.project_modules)
        self.project_classes = list(self.analyzer.project_classes)
        self.project_functions = list(self.analyzer.project_functions)
        self.project_parameters = list(self.analyzer.project_parameters)

    def _filter_name_prefix(self, definitions):
        return [d for d in definitions if d.qname.startswith(self.prefix)]

    @property
    def attributeless_parameters(self):
        """Parameters that has no accessed attributes."""
        return [p for p in self.project_parameters if not p.attributes]

    @property
    def undefined_type_parameters(self):
        """Parameters with accessed attributes but no inferred types."""
        return [p for p in self.project_parameters if p.attributes and not p.suggested_types]

    @property
    def exact_type_parameters(self):
        """Parameters with exactly on inferred type."""
        return [p for p in self.project_parameters if len(p.suggested_types) == 1]

    @property
    def scattered_type_parameters(self):
        """Parameters with more than one inferred type."""
        return [p for p in self.project_parameters if len(p.suggested_types) > 1]

    @property
    def unused_parameters(self):
        """Parameters that has no attributes and which values not
        used directly in function.
        """
        return [p for p in self.attributeless_parameters if not p.used_directly]

    def most_attributes_parameters(self, n):
        return heapq.nlargest(n, self.project_parameters, key=lambda x: len(x.attributes))

    def most_types_parameters(self, n):
        return heapq.nlargest(n, self.scattered_type_parameters,
                              key=lambda x: len(x.suggested_types))

    def as_dict(self, with_samples=False, sample_size=20):
        invisible = object()

        def filter_invisible(obj):
            if isinstance(obj, dict):
                filtered = {}
                for key, value in obj.items():
                    if value is not invisible:
                        filtered[key] = filter_invisible(value)
                return filtered
            elif isinstance(obj, list):
                filtered = []
                for item in obj:
                    if item is not invisible:
                        filtered.append(filter_invisible(item))
                return filtered
            return obj


        def sample(items):
            if not with_samples:
                return invisible

            items = list(map(str, items))
            if len(items) < sample_size:
                return items
            return items[:sample_size]

        def rate(items, population, sample_items=None, with_samples=with_samples):
            d = {
                'total': len(items),
                'rate': len(items) / len(population) if items else 0
            }
            if with_samples:
                if sample_items is None:
                    sample_items = items
                d['sample'] = sample(sample_items)
            return d

        d = {
            'project_name': self.analyzer.project_name,
            'project_root': self.analyzer.project_root,
            'indexed': {
                'total': {
                    'modules': len(self.modules),
                    'classes': len(self.classes),
                    'functions': len(self.functions),
                    'parameters': len(self.parameters),
                },
                'in_project': {
                    'modules': len(self.project_modules),
                    'classes': len(self.project_classes),
                    'functions': len(self.project_functions),
                    'parameters': len(self.project_parameters),
                }
            },
            'project_statistics': {
                'parameters': {
                    'accessed_attributes': {
                        'max': max(len(p.attributes) for p in self.project_parameters) \
                            if self.project_parameters else 0,
                        'top': sample(self.most_attributes_parameters(sample_size))
                    },
                    'attributeless': {
                        'total': len(self.attributeless_parameters),
                        'rate': len(self.attributeless_parameters) / len(self.project_parameters) \
                            if self.project_parameters else 0,
                        'sample': sample(self.attributeless_parameters),
                        'usages': {
                            'argument': rate(
                                items=[p for p in self.attributeless_parameters
                                       if p.used_as_argument > 0],
                                population=self.attributeless_parameters,
                                with_samples=False
                            ),
                            'operand': rate(
                                items=[p for p in self.attributeless_parameters
                                       if p.used_as_operand > 0],
                                population=self.attributeless_parameters,
                                with_samples=False
                            ),
                            'returned': rate(
                                items=[p for p in self.attributeless_parameters if p.returned > 0],
                                population=self.attributeless_parameters,
                                with_samples=False
                            ),
                            'unused': rate(
                                items=self.unused_parameters,
                                population=self.attributeless_parameters
                            )
                        }
                    },
                    'undefined_type': rate(
                        items=self.undefined_type_parameters,
                        population=self.project_parameters
                    ),
                    'exact_type': rate(
                        items=self.exact_type_parameters,
                        population=self.project_parameters
                    ),
                    'scattered_type': rate(
                        items=self.scattered_type_parameters,
                        population=self.project_parameters
                    )
                },
                'additional': {name: unit.as_dict() for name, unit in
                               self.analyzer.statistics.items()}
            }
        }

        return filter_invisible(d)

    def format_json(self, with_samples=False, sample_size=20):
        return json.dumps(self.as_dict(with_samples, sample_size), indent=2)


    def format_text(self):
        formatted = ''
        if self.show_total:
            formatted += '\nTotal indexed: {} classes with {} attributes, ' \
                         '{} functions with {} parameters'.format(
                len(self.classes),
                len(self.analyzer.indexes['CLASS_ATTRIBUTE_INDEX']),
                len(self.functions),
                len(self.parameters))

            formatted += '\nIn project: {} classes, {} functions with {} parameters'.format(
                len(self.project_classes),
                len(self.project_functions),
                len(self.project_parameters))

        if self.show_prolific_params:
            prolific_params = self.most_attributes_parameters(self.top_size)
            formatted += self._format_list(
                header='Most frequently accessed parameters (top {}):'.format(self.top_size),
                items=prolific_params,
                prefix_func=lambda x: '{:3} attributes'.format(len(x.attributes))
            )

        if self.show_param_types:
            total_params = len(self.project_parameters)
            attributeless_params = self.attributeless_parameters
            total_attributeless = len(attributeless_params)
            total_undefined = len(self.undefined_type_parameters)
            total_inferred = len(self.exact_type_parameters)
            total_scattered = len(self.scattered_type_parameters)
            formatted += textwrap.dedent("""
            Parameters statistic:
              {} ({:.2%}) parameters have no attributes (types cannot be inferred):
              However, of them:
                - {:.2%} used directly somehow (no attribute access or subscripts)
                - {:.2%} passed as arguments to other function
                - {:.2%} used as operands in arithmetic or logical expressions
                - {:.2%} returned from function
              {} ({:.2%}) parameters with accessed attributes, but with no inferred type,
              {} ({:.2%}) parameters with accessed attributes and exactly one inferred type,
              {} ({:.2%}) parameters with accessed attributes and more than one inferred type
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
                items=self.most_types_parameters(self.top_size),
                prefix_func=lambda x: '{:3} types'.format(len(x.suggested_types))
            )

            formatted += self._format_list(
                header='Parameters with accessed attributes, '
                       'but with no suggested classes (first {})'.format(self.top_size),
                items=self.undefined_type_parameters[:self.top_size]
            )

            formatted += self._format_list(
                header='Parameters that have no attributes and not used directly '
                       'elsewhere (first {})'.format(self.top_size),
                items=self.unused_parameters[:self.top_size]
            )

        if self.show_random_inferred:
            params = list(self._filter_name_prefix(self.exact_type_parameters))
            quantity = min(self.top_size, len(params))
            formatted += self._format_list(
                header='Parameters with definitively inferred types '
                       '(random {}, total {})'.format(quantity, len(params)),
                items=random.sample(params, quantity)
            )

        if self.dump_classes:
            classes = self._filter_name_prefix(self.project_classes)
            formatted += self._format_list(header='Classes:', items=classes)
        if self.dump_functions:
            functions = self._filter_name_prefix(self.project_functions)
            formatted += self._format_list(header='Functions:', items=functions)
        if self.dump_params:
            parameters = self._filter_name_prefix(self.project_parameters)
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
        return self.format_text()

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