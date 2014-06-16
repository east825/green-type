from __future__ import unicode_literals, print_function, division
import argparse
import ast
import functools
import heapq
import importlib
import inspect
import json
import logging
from contextlib import contextmanager
from collections import defaultdict
import operator
import os
import sys
import textwrap

from . import ast_utils
from . import utils
import timeit
import traceback
import itertools
from .utils import memoized, MISSING, recursion_guard
from .compat import PY2, BUILTINS_NAME, indent, open


try:
    import configparser
except ImportError:
    import ConfigParser as configparser

try:
    from UserDict import UserDict
except ImportError:
    from collections import UserDict

PROJECT_NAME = 'greentype'
CONFIG_NAME = '{}.cfg'.format(PROJECT_NAME)
EXCLUDED_DIRECTORIES = frozenset(['.svn', 'CVS', '.bzr', '.hg', '.git', '__pycache__'])

LOG = logging.getLogger(__name__)
LOG.propagate = False
LOG.setLevel(logging.DEBUG)
LOG.addHandler(logging.NullHandler())


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
    __slots__ = ('_items', '_counter')

    def __init__(self):
        self._counter = itertools.count()
        # tie breaker if item metadata doesn't support comparison
        self._items = []

    def add(self, item, meta_data=None):
        self._items.append((item, next(self._counter), meta_data))

    def min(self, key=lambda x: x):
        item, _, meta = min(self._items, key=lambda x: key(x[0]))
        return item, meta

    def max(self, key=lambda x: x):
        item, _, meta = max(self._items, key=lambda x: key(x[0]))
        return item, meta

    def mean(self):
        return sum(item[0] for item in self._items) / len(self._items)

    def as_dict(self):
        d = {}
        d['min'], d['min_meta'] = self.min()
        d['max'], d['max_meta'] = self.max()
        d['mean'] = self.mean()
        return d

    def __str__(self):
        min_item, min_meta = self.min()
        max_item, max_meta = self.max()
        return 'min={} ({}) ' \
               'max={} ({}) ' \
               'mean={}'.format(min_item, min_meta, max_item, max_meta, self.mean())

    def __repr__(self):
        return str(self)


class Config(UserDict):
    """Configuration similar to the one used in Flask."""

    def __init__(self, defaults, section_name):
        UserDict.__init__(self, defaults.copy())
        self.section_name = section_name

    def merge(self, other):
        self.data = utils.dict_merge(self.data, other, override=True)

    def update_from_object(self, obj):
        filtered = {k: v for k, v in vars(obj).items() if k in self.data}
        self.merge(filtered)

    def update_from_cfg_file(self, path):
        # Not that only source roots are supported for now
        config = configparser.ConfigParser()
        config.optionxform = str.upper
        config.read(path)
        # location of config determine project root
        filtered = {}
        for name in config.options(self.section_name):
            if name not in self:
                continue
            if isinstance(self[name], list):
                filtered[name] = config.get(self.section_name, name).split(':')
            elif isinstance(self[name], bool):
                filtered[name] = config.getboolean(self.section_name, name)
            elif isinstance(self[name], int):
                filtered[name] = config.getint(self.section_name, name)
            elif isinstance(self[name], float):
                filtered[name] = config.getfloat(self.section_name, name)
            else:
                filtered[name] = config.get(self.section_name, name)
        self.merge(filtered)


class GreenTypeAnalyzer(object):
    def __init__(self, target_path):
        defaults = {
            'FOLLOW_IMPORTS': True,
            'BUILTINS': list(sys.builtin_module_names),

            'TARGET_NAME': None,
            'TARGET_PATH': None,

            'PROJECT_ROOT': None,
            'PROJECT_NAME': None,
            'SOURCE_ROOTS': [],
            'EXCLUDE': [],
            'INCLUDE': [],

            'VERBOSE': False,
            'QUIET': False,
            'ANALYZE_BUILTINS': True
        }
        if PY2:
            defaults['BUILTINS'] += ['_socket', 'datetime', '_collections']

        self.indexes = {
            'MODULE_INDEX': Index(None),
            'CLASS_INDEX': Index(None),
            'FUNCTION_INDEX': Index(None),
            'PARAMETER_INDEX': Index(None),
            'CLASS_ATTRIBUTE_INDEX': Index(set)
        }
        if PY2:
            self.register_class(PY2_FAKE_OBJECT)

        self.config = Config(defaults, PROJECT_NAME)
        target_path = os.path.abspath(target_path)
        self.config['TARGET_PATH'] = target_path
        if os.path.isfile(target_path):
            project_root = os.path.dirname(target_path)
        elif os.path.isdir(target_path):
            project_root = target_path
        else:
            raise ValueError('Unrecognized target "{}". '
                             'Should be either file or directory.'.format(target_path))
        self.config['PROJECT_ROOT'] = project_root
        self.config['PROJECT_NAME'] = os.path.basename(target_path)

        self._broken_modules = set()
        self.statistics = defaultdict(StatisticUnit)

        self.statistics['total_project_expressions'] = 0
        self.statistics['total_project_parameter_refs'] = 0
        self.statistics['total_project_parameters'] = 0


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
        result = self._absolutize_paths(self.config['SOURCE_ROOTS'])
        if not self.project_root in result:
            result.insert(0, self.project_root)
        return result

    @property
    def included(self):
        return self._absolutize_paths(self.config['INCLUDE'])

    @property
    def excluded(self):
        return self._absolutize_paths(self.config['EXCLUDE'])

    def _project_definitions(self, defs):
        return [d for d in defs if d.module and self.is_inside_project(d.module.path)]

    def _absolutize_paths(self, paths):
        result = []
        for path in paths:
            if not os.path.isabs(path):
                path = os.path.join(self.project_root, path)
            result.append(os.path.normpath(path))
        return result

    def is_excluded(self, path):
        path = os.path.abspath(path)
        # TODO: use globs/regexes for greater flexibility
        if any(path.startswith(prefix) for prefix in self.included):
            return False
        if any(path.startswith(prefix) for prefix in self.excluded):
            return True
        return False

    def is_inside_project(self, path):
        path = os.path.abspath(path)
        return path.startswith(self.project_root) and not self.is_excluded(path)

    @property
    def project_modules(self):
        return self._project_definitions(self.indexes['MODULE_INDEX'].values())

    @property
    def project_classes(self):
        return self._project_definitions(self.indexes['CLASS_INDEX'].values())

    @property
    def project_functions(self):
        return self._project_definitions(self.indexes['FUNCTION_INDEX'].values())

    @property
    def project_parameters(self):
        return self._project_definitions(self.indexes['PARAMETER_INDEX'].values())

    def invalidate_indexes(self):
        for index in self.indexes.values():
            index.clear()

    def report(self, msg, verbose=False):
        if not self.config['QUIET']:
            if not verbose or self.config['VERBOSE']:
                print(msg)
        LOG.info(msg)

    def report_error(self, msg):
        print(msg, file=sys.stderr)
        LOG.error(msg)


    def index_project(self):
        self.report('Indexing project "{}" starting from "{}".'.format(self.project_root,
                                                                       self.target_path))
        self.report('Source roots: {}.'.format(', '.join(self.source_roots)), verbose=True)

        LOG.debug('Python path: %s', sys.path)
        if os.path.isfile(self.target_path):
            if not utils.is_python_source_module(self.target_path):
                raise ValueError('Not a valid Python module "{}" '
                                 '(should end with .py).'.format(self.target_path))
            self.index_module(path=self.target_path)
        elif os.path.isdir(self.target_path):
            for dirpath, dirnames, filenames in os.walk(self.target_path):
                for name in dirnames[:]:
                    abs_path = os.path.abspath(os.path.join(dirpath, name))
                    if name in EXCLUDED_DIRECTORIES:
                        LOG.debug('Excluded directory "%s". Skipping.', abs_path)
                        dirnames.remove(name)
                for name in filenames:
                    abs_path = os.path.abspath(os.path.join(dirpath, name))
                    if not utils.is_python_source_module(abs_path) or \
                            not self.is_inside_project(abs_path):
                        continue
                    self.index_module(abs_path)


    def index_module(self, path=None, name=None):
        if name is None and path is None:
            raise ValueError('Either module name or module path should be given.')

        if name in self._broken_modules or path in self._broken_modules:
            return None

        if path is not None:
            try:
                name = self.path_to_module_name(path)
            except ValueError:
                LOG.warning('Module "%s" is unreachable from sources roots', path)
                self._broken_modules.add(path)
                return None
        else:
            try:
                path = self.module_name_to_path(name)
            except ValueError:
                LOG.warning('Module %s is not found under source roots', name)
                self._broken_modules.add(name)
                return None

        loaded = self.indexes['MODULE_INDEX'].get(name)
        if loaded:
            return loaded

        if self.is_excluded(path):
            LOG.debug('File "%s" is explicitly excluded from project', path)
            return None

        try:
            module_indexed = SourceModuleIndexer(self, path, name).run()
        except SyntaxError:
            self.report_error('Syntax error during indexing of "{}". '
                              'Wrong Python version?'.format(path))
            LOG.error(traceback.format_exc())
            self._broken_modules.add(path)
            return None

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
                relative = os.path.relpath(path, src_root)
                if not all(os.path.exists(os.path.join(dir, '__init__.py'))
                           for dir in utils.parent_directories(path, src_root)):
                    continue

                dir_name, base_name = os.path.split(relative)
                if base_name == '__init__.py':
                    prepared = dir_name
                else:
                    prepared, _ = os.path.splitext(relative)
                # critical on Windows: foo.bar.py and foo.Bar.py are the same module
                prepared = os.path.normcase(prepared)
                return prepared.replace(os.path.sep, '.').strip('.')
        raise ValueError('Unresolved module: path="{}"'.format(path))


    def module_name_to_path(self, module_name):
        rel_path = os.path.normcase(os.path.join(*module_name.split('.')))
        roots = self.source_roots + [p for p in sys.path if p not in ('', '.', os.getcwd())]
        for src_root in roots:
            path = os.path.join(src_root, rel_path)
            package_path = os.path.join(path, '__init__.py')
            module_path = path + '.py'
            if os.path.isfile(package_path):
                path = package_path
            elif os.path.isfile(module_path):
                path = module_path
            else:
                continue

            if all(os.path.exists(os.path.join(dir, '__init__.py'))
                   for dir in utils.parent_directories(path, src_root)):
                return path

        raise ValueError('Unresolved module: name="{}"'.format(module_name))


    def index_builtins(self):
        def object_name(obj):
            return obj.__name__ if PY2 else obj.__qualname__

        for module_name in self.config['BUILTINS']:
            LOG.debug('Reflectively analyzing %s', module_name)

            module = importlib.import_module(module_name, None)
            for module_attr_module_name, module_attr in vars(module).items():
                if inspect.isclass(module_attr):
                    cls = module_attr
                    class_name = module_name + '.' + object_name(cls)
                    bases = tuple(object_name(b) for b in cls.__bases__)
                    attributes = set(vars(cls))
                    self.register_class(ClassDef(class_name, None, None, bases, attributes))

    @memoized
    @recursion_guard(None)
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
        df = check_loaded(name) or check_loaded(BUILTINS_NAME + '.' + name)
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
                        if module_loaded and module_loaded is not module:
                            # drop local name (alias) for imports like
                            # import module as alias
                            # print(alias.MyClass.InnerClass())
                            top_level_name = utils.qname_drop(name, imp.local_name)
                            df = self.resolve_name(top_level_name, module_loaded, type)
                            if df:
                                return df
                            LOG.info('Module %s referenced as "import %s" in "%s" loaded '
                                     'successfully, but definition of %s not found',
                                     imp.imported_name, imp.imported_name, module.path, qname)
                    else:
                        # first, interpret import like 'from module import Name'
                        module_name = utils.qname_tail(imp.imported_name)
                        module_loaded = self.index_module(name=module_name)
                        if module_loaded and module_loaded is not module:
                            top_level_name = utils.qname_drop(qname, module_name)
                            df = self.resolve_name(top_level_name, module_loaded, type)
                            if df:
                                return df
                        # then, as 'from package import module'
                        module_loaded = self.index_module(name=imp.imported_name)
                        if module_loaded and module_loaded is not module:
                            top_level_name = utils.qname_drop(name, imp.local_name)
                            df = self.resolve_name(top_level_name, module_loaded, type)
                            if df:
                                return df
                            LOG.info('Module %s referenced as "from %s import %s" in "%s" loaded '
                                     'successfully, but definition of %s not found',
                                     imp.imported_name, utils.qname_tail(imp.imported_name),
                                     utils.qname_head(imp.imported_name), module.path,
                                     qname)
                elif imp.star_import:
                    module_loaded = self.index_module(name=imp.imported_name)
                    if module_loaded and module_loaded is not module:
                        # no aliased allowed with 'from module import *' so we check directly
                        # for name searched in the first place
                        df = self.resolve_name(name, module_loaded, type)
                        if df:
                            return df

        LOG.warning('Cannot resolve name %s in module "%s"', name,
                    module.path if module else '<undefined>')

    @memoized
    def _resolve_bases(self, class_def):
        LOG.debug('Resolving bases for %s', class_def.qname)
        bases = set()

        for name in class_def.bases:
            if name == class_def.name:
                LOG.warning("Class %s uses base with the same name. Not supported "
                            "until flow-insensitive analysis is done.", class_def.qname)
                continue
            base_def = self.resolve_name(name, class_def.module, 'class')
            if base_def:
                bases.add(base_def)
                bases.update(self._resolve_bases(base_def))
            else:
                LOG.warning('Base class %s of %s not found', name, class_def.qname)
        return bases

    def infer_parameter_types(self):
        for param in self.project_parameters:
            if param.attributes:
                param.suggested_types = self.suggest_classes(param.attributes)
                # self._resolve_bases.clear_results()


    def suggest_classes(self, accessed_attrs):
        def unite(sets):
            return functools.reduce(set.union, sets, set())

        def intersect(sets):
            return functools.reduce(set.intersection, sets) if sets else set()

        # More fair algorithm because it considers newly discovered bases classes as well
        index = self.indexes['CLASS_ATTRIBUTE_INDEX']
        candidates = unite(index[attr] for attr in accessed_attrs)

        self.statistics['initial_candidates'].add(len(candidates), list(accessed_attrs))

        suitable = set()
        checked = set()
        total = 0
        while candidates:
            candidate = candidates.pop()
            total += 1
            checked.add(candidate)
            bases = self._resolve_bases(candidate)

            # register number of base classes for statistics
            self.statistics['class_bases'].add(len(bases), candidate.qname)

            available_attrs = unite(b.attributes for b in bases) | candidate.attributes
            if accessed_attrs <= available_attrs:
                suitable.add(candidate)

            # new classes could be added to index during call to _resolve_bases(),
            # so we have to check them as well
            if not self.config['FOLLOW_IMPORTS']:
                for base in bases:
                    if base in checked:
                        continue
                    if any(attr in base.attributes for attr in accessed_attrs):
                        candidates.add(base)

        self.statistics['total_candidates'].add(total, list(accessed_attrs))

        # remove subclasses if their superclasses is suitable also
        for cls in suitable.copy():
            if any(base in suitable for base in self._resolve_bases(cls)):
                suitable.remove(cls)

        return suitable

    def discover_project_config(self):
        for parent_dir in utils.parent_directories(self.target_path, strict=False):
            config_path = os.path.join(parent_dir, CONFIG_NAME)
            if os.path.exists(config_path):
                self.report('Found config file at "{}".'.format(config_path), verbose=True)
                self.config.update_from_cfg_file(config_path)
                self.config['PROJECT_ROOT'] = os.path.dirname(config_path)
                break

    def register_class(self, class_def):
        self.indexes['CLASS_INDEX'][class_def.qname] = class_def

        if class_def.qname not in (BUILTINS_NAME + '.object', PY2_FAKE_OBJECT.qname):
            class_def.attributes -= {'__doc__'}
            # safe only on Python 3
            if not PY2:
                class_def.attributes.discard('__init__')

        for attr in class_def.attributes:
            self.indexes['CLASS_ATTRIBUTE_INDEX'][attr].add(class_def)

    def register_function(self, func_def):
        self.indexes['FUNCTION_INDEX'][func_def.qname] = func_def
        for param_def in func_def.parameters:
            self.indexes['PARAMETER_INDEX'][param_def.qname] = param_def

    def register_module(self, module_def):
        self.indexes['MODULE_INDEX'][module_def.qname] = module_def

    @classmethod
    def main(cls):
        parser = argparse.ArgumentParser()
        parser.add_argument('--src-roots', type=lambda x: x.split(':'), default=[],
                            dest='SOURCE_ROOTS',
                            help='Sources roots separated by colon.')

        parser.add_argument('--exclude', type=lambda x: x.split(':'), default=[],
                            dest='EXCLUDE',
                            help='Files excluded from indexing process.')

        parser.add_argument('--include', type=lambda x: x.split(':'), default=[],
                            dest='INCLUDE',
                            help='Files included to indexing process.')

        parser.add_argument('-t', '--target', default='',
                            dest='TARGET_NAME',
                            help='Target qualifier to restrict output.')

        parser.add_argument('-L', '--follow-imports', action='store_true',
                            dest='FOLLOW_IMPORTS',
                            help='Follow imports during indexing.')

        parser.add_argument('-B', '--no-builtins', action='store_false',
                            dest='ANALYZE_BUILTINS',
                            help='Not analyze built-in modules reflectively first.')

        parser.add_argument('--with-samples', action='store_true',
                            help='Include samples in report.')

        parser.add_argument('-d', '--dump-params', action='store_true',
                            help='Dump parameters qualified by target.')

        parser.add_argument('-v', '--verbose', action='count', default=0,
                            dest='verbose_level',
                            help='Enable verbose output.')

        parser.add_argument('-o', '--output', type=argparse.FileType(mode='w'), default=str('-'),
                            help='File, where to write report.')

        # TODO: detect piping
        parser.add_argument('-q', '--quiet', action='store_true',
                            dest='QUIET',
                            help='Print only report in console.')

        parser.add_argument('--json', action='store_true',
                            help='Dump analysis results in JSON.')

        parser.add_argument('path',
                            help='Path to single Python module or directory.')

        args = parser.parse_args()

        if args.verbose_level > 1:
            console = logging.StreamHandler()
            console.setLevel(logging.INFO)
            LOG.addHandler(console)
        args.VERBOSE = args.verbose_level > 0

        analyzer = cls(os.path.abspath(os.path.expanduser(args.path)))
        analyzer.config['VERBOSE'] = args.VERBOSE
        analyzer.discover_project_config()
        analyzer.config.update_from_object(args)

        if analyzer.config['ANALYZE_BUILTINS']:
            analyzer.index_builtins()

        analyzer.index_project()

        start = timeit.default_timer()
        analyzer.infer_parameter_types()
        analyzer.report('Inferred types for parameters in '
                        '{:.2f}'.format(timeit.default_timer() - start))

        statistics = analyzer.statistics_report()
        LOG.info('Writing report to "%s"', args.output.name)
        with args.output as f:
            if args.json:
                report = statistics.format_json(with_samples=args.with_samples)
            else:
                report = statistics.format_text(with_samples=args.with_samples,
                                                dump_params=args.dump_params)
            f.write(report)


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
        return 'module {} at "{}"'.format(self.qname, self.path)


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


PY2_FAKE_OBJECT = ClassDef('PY2_FAKE_OBJECT', None, None, (), {'__doc__', '__module__'})


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
            s = '{} ~ {}'.format(s, ' | '.join(cls.qname for cls in self.suggested_types))
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
        if not isinstance(parent, (ast.Attribute, ast.Subscript)) \
                and not isinstance(node.ctx, (ast.Store, ast.Del, ast.Param)):
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
    def __init__(self, analyzer, path, name=None):
        self.analyzer = analyzer
        self.indexes = analyzer.indexes
        self.module_path = os.path.abspath(path)

        if name is None:
            self.module_name = analyzer.path_to_module_name(path)
        else:
            self.module_name = name

        self.scopes_stack = []
        self.module_def = None
        self.depth = 0
        self.root = None

    def register(self, definition):
        if isinstance(definition, ClassDef):
            self.analyzer.register_class(definition)
        elif isinstance(definition, FunctionDef):
            self.analyzer.register_function(definition)
        raise TypeError('Unknown definition: {}'.format(definition))

    def qualified_name(self, node):
        node_name = ast_utils.node_name(node)
        scope_owner = self.parent_scope()
        if scope_owner:
            return scope_owner.qname + '.' + node_name
        return node_name

    def run(self):
        LOG.debug('Indexing module "%s"', self.module_path)
        # let ast deal with encoding by itself
        with open(self.module_path, mode='br') as f:
            self.root = ast.parse(f.read(), self.module_path)
        ast_utils.interlink_ast(self.root)
        self.visit(self.root)
        return self.module_def

    def visit(self, node):
        self.depth += 1
        try:
            if isinstance(node, ast.expr) and self.analyzer.is_inside_project(self.module_path):
                if not hasattr(node, 'ctx'):
                    self.analyzer.statistics['total_project_expressions'] += 1

                elif not isinstance(node.ctx, (ast.Store, ast.Del, ast.Param)):
                    self.analyzer.statistics['total_project_expressions'] += 1
                    if isinstance(node, ast.Name):
                        for definition in reversed(self.scopes_stack):
                            if isinstance(definition, FunctionDef) and node.id in \
                                    {p.name for p in definition.parameters}:
                                self.analyzer.statistics['total_project_parameter_refs'] += 1
                                break

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
                                    'file="{}" module={}, level={}'.format(self.module_path,
                                                                           child.module,
                                                                           child.level))
                for alias in child.names:
                    if alias.name == '*':
                        imports.append(Import(target_module, None, True, True))
                    else:
                        imported_name = '{}.{}'.format(target_module, alias.name)
                        imports.append(
                            Import(imported_name, alias.asname or alias.name, True, False))
        module_def = ModuleDef(self.module_name, node, self.module_path, imports)
        self.analyzer.register_module(module_def)
        return module_def

    def class_discovered(self, node):
        class_name = self.qualified_name(node)
        bases_names = []
        if not node.bases:
            if PY2:
                bases_names.append(PY2_FAKE_OBJECT.qname)
            else:
                bases_names.append(BUILTINS_NAME + '.object')

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
        self.analyzer.register_class(class_def)
        return class_def

    def function_discovered(self, node):
        func_name = self.qualified_name(node)
        args = node.args

        if isinstance(self.parent_scope(), ClassDef) and \
                not ast_utils.decorated_with(node, 'staticmethod'):
            declared_params = args.args[1:]
        else:
            declared_params = args.args[:]
        # Python += update lists inplace
        declared_params += [args.vararg, args.kwarg]

        # TODO: filter out parameter patterns in Python 2?
        total_parameters = len(args.args) + bool(args.vararg) + bool(args.kwarg)

        if not PY2:
            declared_params += args.kwonlyargs
            total_parameters += len(args.kwonlyargs)

        if self.analyzer.is_inside_project(self.module_path):
            self.analyzer.statistics['total_project_parameters'] += total_parameters

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
        self.analyzer.register_function(func_def)
        return func_def


class StatisticsReport(object):
    def __init__(self, analyzer):
        self.analyzer = analyzer
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
        def sample(items):
            if not with_samples:
                return MISSING

            return list(items)[:sample_size]

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
                            if self.attributeless_parameters else 0,
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
                        population=self.project_parameters,
                        sample_items=self.most_types_parameters(sample_size)
                    )
                },
                'additional': {name: unit.as_dict() if isinstance(unit, StatisticUnit) else unit
                               for name, unit in self.analyzer.statistics.items()}
            }
        }

        return utils.deep_filter(lambda x: x is not MISSING, d)

    def format_json(self, with_samples=False, sample_size=20, expand_definitions=True):
        class Dumper(json.JSONEncoder):
            def default(self, o):
                if expand_definitions:
                    if isinstance(o, ParameterDef):
                        return {
                            'qualified_name': o.qname,
                            'accessed_attributes': list(o.attributes),
                            'suggested_classes': [cls.qname for cls in o.suggested_types]
                        }
                    elif isinstance(o, ClassDef):
                        return {
                            'qualified_name': o.qname,
                            'bases': list(o.bases),
                            'declared_attributes': list(o.attributes)
                        }
                    elif isinstance(o, FunctionDef):
                        return {
                            'qualified_name': o.qname,
                            'parameters': [p.name for p in o.parameters]
                        }
                    elif isinstance(o, ModuleDef):
                        return {
                            'qualified_name': o.qname,
                            'path': o.path
                        }
                return super(Dumper, self).default(o)

        return json.dumps(self.as_dict(with_samples, sample_size), cls=Dumper, indent=2)


    def format_text(self, with_samples=True, samples_size=20, dump_classes=False,
                    dump_functions=False, dump_params=False):
        d = self.as_dict(with_samples, samples_size)
        formatted = '\nTotal indexed: ' \
                    '{} classes, ' \
                    '{} functions with {} parameters'.format(
            d['indexed']['total']['classes'],
            d['indexed']['total']['functions'],
            d['indexed']['total']['parameters'])

        formatted += '\nIn project: ' \
                     '{} classes, ' \
                     '{} functions with {} parameters'.format(
            d['indexed']['in_project']['classes'],
            d['indexed']['in_project']['functions'],
            d['indexed']['in_project']['parameters'])

        if with_samples:
            formatted += self._format_list(
                header='Most frequently accessed parameters (top {}):'.format(samples_size),
                items=d['project_statistics']['parameters']['accessed_attributes']['top'],
                prefix_func=lambda x: '{:3} attributes'.format(len(x.attributes))
            )

        stat = d['project_statistics']['parameters']
        formatted += textwrap.dedent("""
        Parameters statistic:
          {} ({:.2%}) parameters have no attributes (types cannot be inferred):
          However, of them:
            - {:.2%} passed as arguments to other function
            - {:.2%} used as operands in arithmetic or logical expressions
            - {:.2%} returned from function
            - {:.2%} unused
          {} ({:.2%}) parameters with accessed attributes, but with no inferred type,
          {} ({:.2%}) parameters with accessed attributes and exactly one inferred type,
          {} ({:.2%}) parameters with accessed attributes and more than one inferred type
        """.format(
            stat['attributeless']['total'], stat['attributeless']['rate'],
            stat['attributeless']['usages']['argument']['rate'],
            stat['attributeless']['usages']['operand']['rate'],
            stat['attributeless']['usages']['returned']['rate'],
            stat['attributeless']['usages']['unused']['rate'],
            stat['undefined_type']['total'], stat['undefined_type']['rate'],
            stat['exact_type']['total'], stat['exact_type']['rate'],
            stat['scattered_type']['total'], stat['scattered_type']['rate']
        ))

        if with_samples:
            formatted += self._format_list(
                header='Parameters with scattered type (top {}):'.format(samples_size),
                items=stat['scattered_type']['sample'],
                prefix_func=lambda x: '{:3} types'.format(len(x.suggested_types))
            )

            formatted += self._format_list(
                header='Parameters with accessed attributes, '
                       'but with no suggested classes (first {}):'.format(samples_size),
                items=stat['undefined_type']['sample']
            )

            formatted += self._format_list(
                header='Parameters that have no attributes and not used directly '
                       'elsewhere (first {}):'.format(samples_size),
                items=stat['attributeless']['usages']['unused']['sample']
            )

            formatted += self._format_list(
                header='Parameters with definitively inferred types '
                       '(first {}):'.format(samples_size),
                items=stat['exact_type']['sample'],
            )

        if dump_classes:
            classes = self._filter_name_prefix(self.project_classes)
            formatted += self._format_list(header='Classes:', items=classes)
        if dump_functions:
            functions = self._filter_name_prefix(self.project_functions)
            formatted += self._format_list(header='Functions:', items=functions)
        if dump_params:
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

        formatted += self._format_list(
            header='Additional statistics:',
            items=('{}: {}'.format(k, str(v)) for k, v in self.analyzer.statistics.items())
        )
        return formatted

    def __str__(self):
        return self.format_text()

    def __repr__(self):
        return 'Statistic(project="{}")'.format(self.analyzer.project_root)

    def _format_list(self, items, header=None, prefix_func=None, indentation='  '):
        formatted = '\n'
        if header is not None:
            formatted += '{}\n'.format(header)
        if not items:
            formatted += indentation + 'none'
        else:
            blocks = []
            for item in items:
                item_text = str(item)
                if prefix_func is not None:
                    prefix = '{}{} : '.format(indentation, prefix_func(item))
                    lines = item_text.splitlines()
                    first_line, remaining_lines = lines[0], lines[1:]
                    block = '{}{}'.format(prefix, first_line)
                    if remaining_lines:
                        indented_tail = indent('\n'.join(remaining_lines), ' ' * len(prefix))
                        blocks.append('{}\n{}'.format(block, indented_tail))
                    else:
                        blocks.append(block)
                else:
                    blocks.append(indent(item_text, indentation))
            formatted += '\n'.join(blocks)
        return formatted + '\n'