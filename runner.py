from __future__ import unicode_literals, print_function

import os
import logging
import argparse
import time
import sys

from greentype import core
from greentype import utils


logging.basicConfig(level=logging.CRITICAL)
LOG = logging.getLogger(__name__)


def analyze(path, target, recursively=True, builtins=True, dump_params=False):
    if builtins:
        print('Analysing built-in modules...')
        core.index_builtins()

    print('Analyzing user modules starting from {!r}'.format(path))
    if os.path.isfile(path):
        if not utils.is_python_source_module(path):
            raise ValueError('Not a valid Python module {!r} (should end with .py).'.format(path))
        core.index_module_by_path(path, recursively)
    elif os.path.isdir(path):
        for dirpath, dirnames, filenames in os.walk(path):
            for name in dirnames:
                abs_path = os.path.abspath(os.path.join(dirpath, name))
                if not os.path.exists(os.path.join(abs_path, '__init__.py')):
                    # ignore namespace packages for now
                    LOG.debug('Not a package: %r. Skipping.', abs_path)
                    dirnames.remove(name)
                if name.startswith('.'):
                    LOG.debug('Hidden directory: %r. Skipping.', abs_path)
                    dirnames.remove(name)
            for name in filenames:
                abs_path = os.path.abspath(os.path.join(dirpath, name))
                if not utils.is_python_source_module(abs_path):
                    continue
                core.index_module_by_path(abs_path, recursively)

    # time.process_time() in Python 3.3
    start_time = time.clock()
    print('Started inferring parameter types')
    # TODO: analyze newly found functions as well
    for func in set(core.Indexer.FUNCTION_INDEX.values()):
        for param in func.parameters:
            param.suggested_types = core.suggest_classes_by_attributes(param.attributes)
    print('Stopped inferring: {:.2f}s spent\n'.format(time.clock() - start_time))
    print(core.Statistic(dump_params=dump_params, prefix=target))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--src-roots', help='Sources roots separated by colon.')
    parser.add_argument('-t', '--target',  default='', help='Target qualifier to restrict output.')
    parser.add_argument('-r', '--recursively', action='store_true',
                        help='Follow imports during indexing.')
    parser.add_argument('-B', '--no-builtins', action='store_true',
                        help='Not analyze built-in modules reflectively first.')
    parser.add_argument('-d', '--dump-parameters', action='store_true',
                        help='Dump parameters qualified by target')
    parser.add_argument('-v', '--verbose', action='store_true', help='Enable DEBUG logging level.')
    parser.add_argument('path', help='Path to single Python module or directory.')
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    def normalize(path):
        return os.path.abspath(os.path.expanduser(path))

    try:
        target_path = normalize(args.path)

        if not args.src_roots:
            if os.path.isfile(target_path):
                core.SRC_ROOTS.append(os.path.dirname(target_path))
            elif os.path.isdir(target_path):
                core.SRC_ROOTS.append(target_path)
            else:
                raise ValueError('Unrecognized target {!r}. Should be either file or directory.'.format(target_path))
        else:
            core.SRC_ROOTS.extend(map(normalize, args.src_roots.split(':')))
        analyze(target_path,
                target=args.target,
                recursively=args.recursively,
                builtins=not args.no_builtins,
                dump_params=args.dump_parameters)
    except Exception as e:
        LOG.exception(e)


if __name__ == '__main__':
    main()
