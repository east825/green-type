import functools
import os
import logging
import argparse
import sys
import time

from greentype import core

from greentype import utils
from greentype.core import Statistic, index_module_by_path


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



def suggest_classes(struct_type):
    def unite(sets):
        return functools.reduce(set.union, sets, set())

    def intersect(sets):
        if not sets:
            return {}
        return functools.reduce(set.intersection, sets)

    def load_module(module_name):
        try:
            return index_module_by_path(core.module2path(module_name))
        except ValueError:
            LOG.warning('Cannot find module for name %r', module_name)
        return None


    @utils.memo
    def resolve_bases(class_def):
        LOG.debug('Resolving bases for %r', class_def.qname)
        bases = set()

        def check_class_loaded(qname, module=None):
            class_def = core.Indexer.CLASS_INDEX.get(qname)
            # check amongst imported definitions of module
            if not class_def and module:
                short_name = utils.qname_head(qname)
                class_def = module.definitions.get(short_name)
            if class_def:
                bases.add(class_def)
                bases.update(resolve_bases(class_def))
                return True
            return False

        for ref in class_def.bases:
            # fully qualified name or built-in
            base_qname = ref
            if check_class_loaded(base_qname):
                continue
            module = class_def.module
            # not built-in
            if module:
                # name defined in the same module
                base_qname = module.qname + '.' + ref
                if check_class_loaded(base_qname, module):
                    continue
                # name is imported
                for imp in module.imports:
                    if imp.imports_name(ref):
                        base_qname = utils.qname_merge(imp.local_name, ref)
                        # TODO: more robust qualified name handling
                        base_qname = base_qname.replace(imp.local_name, imp.imported_name, 1)
                        # Case 1:
                        # >>> import some.module as alias
                        # index some.module, then check some.module.Base
                        # Case 2:
                        # >>> from some.module import Base as alias
                        # index some.module, then check some.module.Base
                        # if not found index some.module.Base, then check some.module.Base again
                        if check_class_loaded(base_qname, module):
                            break

                        if not imp.import_from:
                            module_loaded = load_module(imp.imported_name)
                            if module_loaded:
                                if not check_class_loaded(base_qname, module_loaded):
                                    LOG.info('Module %r referenced as "import %s" in %r loaded '
                                             'successfully, but class %r not found',
                                             imp.imported_name, imp.imported_name, module.path, base_qname)
                        elif imp.star_import:
                            module_loaded = load_module(imp.imported_name)
                            if module_loaded and check_class_loaded(base_qname, module_loaded):
                                break
                        else:
                            # first, interpret import as 'from module import Name'
                            module_loaded = load_module(utils.qname_tail(imp.imported_name))
                            if module_loaded and check_class_loaded(base_qname, module_loaded):
                                break
                            # then, as 'from package import module'
                            module_loaded = load_module(imp.imported_name)
                            if module_loaded and not check_class_loaded(base_qname, module_loaded):
                                LOG.info('Module %r referenced as "from %s import %s" in %r loaded '
                                         'successfully, but class %r not found',
                                         imp.imported_name, utils.qname_tail(imp.imported_name),
                                         utils.qname_head(imp.imported_name), module.path,
                                         base_qname)

            else:
                LOG.warning('Base class %r of %r not found', class_def.qname, base_qname)
        return bases

    accessed_attrs = struct_type.attributes

    class_pool = {attr: core.Indexer.CLASS_ATTRIBUTE_INDEX[attr] for attr in accessed_attrs}
    if not class_pool:
        return set()
    with_all_attributes = intersect(class_pool.values())
    with_any_attribute = unite(class_pool.values())

    suitable_classes = set(with_all_attributes)
    for class_def in with_any_attribute - with_all_attributes:
        bases = resolve_bases(class_def)
        all_attrs = unite(b.attributes for b in bases) | class_def.attributes
        if accessed_attrs <= all_attrs:
            suitable_classes.add(class_def)

    # remove subclasses if their superclasses is suitable also
    for class_def in suitable_classes.copy():
        if any(base in suitable_classes for base in resolve_bases(class_def)):
            suitable_classes.remove(class_def)

    return suitable_classes


def analyze(path, target):
    if os.path.isfile(path):
        if not utils.is_python_source_module(path):
            raise ValueError('Not a Python module {!r} (should end with .py).'.format(path))
        index_module_by_path(path)
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
                index_module_by_path(abs_path)

    core.ReflectiveModuleIndexer('builtins').run()
    start_time = time.process_time()
    LOG.debug('Started inferring parameter types')
    # TODO: analyze newly found functions as well
    for func in set(core.Indexer.FUNCTION_INDEX.values()):
        for param in func.parameters:
            structural_type = core.StructuralType(param.attributes)
            param.suggested_types = suggest_classes(structural_type)
    LOG.debug('Stopped inferring: %fs spent\n', time.process_time() - start_time)
    print(Statistic(dump_params=True).format(target=target))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--src-roots', help='Sources roots separated by colon.')
    parser.add_argument('--target', help='Target qualifier to restrict output.')
    parser.add_argument('-v', '--verbose', action='store_true', help='Enable DEBUG logging.')
    parser.add_argument('path', help='Path to single Python module or directory.')
    args = parser.parse_args()

    if args.verbose:
        root_logger.setLevel(logging.DEBUG)

    try:
        target_path = os.path.abspath(os.path.expanduser(args.path))

        if not args.src_roots:
            if os.path.isfile(target_path):
                core.SRC_ROOTS.append(os.path.dirname(target_path))
            elif os.path.isdir(target_path):
                core.SRC_ROOTS.append(target_path)
            else:
                raise ValueError('Unrecognized target {!r}. Should be either file or directory.'.format(target_path))
        else:
            core.SRC_ROOTS.extend(args.src_roots.split(':'))
        analyze(target_path, args.target)
    except Exception as e:
        LOG.exception(e)


if __name__ == '__main__':
    main()
