import os
import logging
import argparse
import sys
import time

from greentype import core

from greentype import utils

logging.basicConfig(level=logging.DEBUG)
# root_logger = logging.getLogger()
# root_logger.setLevel(logging.DEBUG)
#
# console_err = logging.StreamHandler(stream=sys.stderr)
# console_err.setLevel(logging.WARNING)
#
# console_info = logging.StreamHandler(stream=sys.stdout)
# console_info.setFormatter(logging.Formatter('%(message)s'))
# console_info.addFilter(lambda x: x.levelno < logging.WARNING)
#
# root_logger.addHandler(console_err)
# root_logger.addHandler(console_info)

LOG = logging.getLogger(__name__)


def analyze(path, target):
    if os.path.isfile(path):
        if not utils.is_python_source_module(path):
            raise ValueError('Not a Python module {!r} (should end with .py).'.format(path))
        core.index_module_by_path(path)
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
                core.index_module_by_path(abs_path)

    core.ReflectiveModuleIndexer('builtins').run()
    start_time = time.process_time()
    LOG.debug('Started inferring parameter types')
    # TODO: analyze newly found functions as well
    for func in set(core.Indexer.FUNCTION_INDEX.values()):
        for param in func.parameters:
            param.suggested_types = core.suggest_classes_by_attributes(param.attributes)
    LOG.debug('Stopped inferring: %fs spent\n', time.process_time() - start_time)
    print(core.Statistic(dump_params=True).format(target=target))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--src-roots', help='Sources roots separated by colon.')
    parser.add_argument('--target', help='Target qualifier to restrict output.')
    parser.add_argument('-v', '--verbose', action='store_true', help='Enable DEBUG logging.')
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
        analyze(target_path, args.target)
    except Exception as e:
        LOG.exception(e)


if __name__ == '__main__':
    main()
