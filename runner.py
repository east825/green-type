import functools
import os
import logging
import argparse
import sys
import heapq
import time
import importlib.util

from greentype import core
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

class Stat:
    @staticmethod
    def total_functions():
        return len(core.Indexer.FUNCTION_INDEX)

    @staticmethod
    def total_classes():
        return len(core.Indexer.CLASS_INDEX)

    @staticmethod
    def total_attributes():
        return len(core.Indexer.CLASS_ATTRIBUTE_INDEX)

    @staticmethod
    def attributeless_parameters():
        return [p for p in core.Indexer.PARAMETERS_INDEX.values() if not p.attributes]


    @staticmethod
    def undefined_parameters():
        return [p for p in core.Indexer.PARAMETERS_INDEX.values() if not p.suggested_types]

    @staticmethod
    def scattered_parameters():
        return [p for p in core.Indexer.PARAMETERS_INDEX.values() if len(p.suggested_types) > 1]

    @staticmethod
    def top_parameters_with_most_attributes(n, exclude_self=True):
        if exclude_self:
            # params = itertools.chain.from_iterable(f.unbound_parameters for f in _functions_index.values())
            params = [p for p in core.Indexer.PARAMETERS_INDEX.values() if p.name != 'self' ]
        else:
            params = core.Indexer.PARAMETERS_INDEX.values()
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
            total = len(core.Indexer.PARAMETERS_INDEX)
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
            log_items(core.Indexer.FUNCTION_INDEX.values(), 'Functions:')
        if all_classes:
            log_items(core.Indexer.CLASS_INDEX.values(), 'Classes:')
        if all_params:
            log_items(core.Indexer.PARAMETERS_INDEX.values(), 'Parameters:')

def analyze_module(path):
    core.SourceModuleIndexer(path).run()


def suggest_classes(structural_type):
    def unite(sets):
        return functools.reduce(set.union, sets, set())

    def intersect(sets):
        if not sets:
            return {}
        return functools.reduce(set.intersection, sets)

    def resolve_bases(class_def):
        module_name = class_def.module_name
        bases = set()
        for base_ref in class_def.bases:
            # base class reference is not qualified
            if '.' not in base_ref:
                # first, look up in the same module
                qname = module_name + '.' + base_ref if module_name else base_ref
                resolved = core.Indexer.CLASS_INDEX.get(qname)
                if resolved:
                    bases.add(resolved)
                    continue
            if module_name:
                module_def = core.Indexer.MODULE_INDEX[module_name]
                for imp in module_def.imports:
                    if imp.imports_name(base_ref):
                        if imp.qname not in core.Indexer.MODULE_INDEX:
                            # handle spec
                            spec = analyze(importlib.util.find_spec(qname))
                    elif imp.star:
                        pass

                base_ref = (module_name + '.' + base_ref)
                if base_ref:
                    pass

        return bases


    class_pool = {attr: core.Indexer.CLASS_ATTRIBUTE_INDEX[attr] for attr in structural_type.attributes}
    if not class_pool:
        return set()
    with_all_attributes = intersect(class_pool.values())
    with_any_attribute = unite(class_pool.values())

    suitable_classes = set(with_all_attributes)
    # resolved_bases = {}
    # for class_def in with_any_attribute - with_all_attributes:
    #     bases = resolve_bases(class_def)
    #     resolved_bases[class_def] = bases
    #     inherited_attributes = unite(b.attributes for b in bases) | {class_def.attributes}
    #     if structural_type.attributes in inherited_attributes:
    #         suitable_classes.add(class_def)
    #
    # for class_def in set(suitable_classes):
    #     for base_class in resolved_bases[class_def]:
    #         if base_class in suitable_classes:
    #             suitable_classes.remove(class_def)

    return suitable_classes


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

    core.ReflectiveModuleIndexer('builtins').run()
    start_time = time.process_time()
    LOG.debug('Started inferring parameter types')
    for func in core.Indexer.FUNCTION_INDEX.values():
        for param in func.parameters:
            structural_type = core.StructuralType(param.attributes)
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
