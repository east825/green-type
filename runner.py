from __future__ import unicode_literals, print_function

import os
import logging
import argparse
import traceback

from greentype import core
from greentype import utils


logging.basicConfig(level=logging.CRITICAL)
LOG = logging.getLogger(__name__)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--src-roots', default='', help='Sources roots separated by colon.')
    parser.add_argument('-t', '--target', default='', help='Target qualifier to restrict output.')
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

        if os.path.isfile(target_path):
            project_root = os.path.dirname(target_path)
        elif os.path.isdir(target_path):
            project_root = target_path
        else:
            raise ValueError('Unrecognized target {!r}. '
                             'Should be either file or directory.'.format(target_path))
        analyzer = core.GreenTypeAnalyzer(project_root=project_root,
                                          source_roots=map(normalize, args.src_roots.split(':')))

        analyzer.config.update(
            TARGET_PATH=target_path,
            TARGET_NAME=args.target,
            ANALYZE_BUILTINS=not args.no_builtins,
            FOLLOW_IMPORTS=args.recursively,
            VERBOSE=args.verbose
        )

        if not args.no_builtins:
            analyzer.index_builtins()

        print('Analyzing user modules starting from {!r}'.format(args.path))
        if os.path.isfile(args.path):
            if not utils.is_python_source_module(args.path):
                raise ValueError('Not a valid Python module {!r} '
                                 '(should end with .py).'.format(args.path))
            analyzer.index_module(path=args.path)
        elif os.path.isdir(args.path):
            for dirpath, dirnames, filenames in os.walk(args.path):
                for name in dirnames:
                    abs_path = os.path.abspath(os.path.join(dirpath, name))
                    if not os.path.exists(os.path.join(abs_path, '__init__.py')):
                        # ignore namespace packages for now
                        LOG.debug('Not a package: %r. Skipping.', abs_path)
                        dirnames.remove(name)
                    elif name.startswith('.'):
                        LOG.debug('Hidden directory: %r. Skipping.', abs_path)
                        dirnames.remove(name)
                for name in filenames:
                    abs_path = os.path.abspath(os.path.join(dirpath, name))
                    if not utils.is_python_source_module(abs_path):
                        continue
                    analyzer.index_module(abs_path)

        # TODO: analyze newly found functions as well
        statistics = analyzer.statistics
        for param in statistics.parameters(True):
            param.suggested_types = analyzer.suggest_classes(param.attributes)
        print(statistics)
    except Exception:
        traceback.print_exc()


if __name__ == '__main__':
    main()
