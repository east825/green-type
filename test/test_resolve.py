from contextlib import contextmanager
from greentype import core
from greentype import utils
import os
import pytest

core.TEST_MODE = True


@pytest.fixture()
def in_resolve_tests_directory():
    os.chdir(os.path.join(os.path.dirname(__file__), 'resolve'))


@pytest.fixture()
def invalidate_caches():
    core.Indexer.CLASS_INDEX.clear()
    core.Indexer.CLASS_ATTRIBUTE_INDEX.clear()
    core.Indexer.FUNCTION_INDEX.clear()
    core.Indexer.PARAMETERS_INDEX.clear()
    core.Indexer.MODULE_INDEX.clear()


pytestmark = pytest.mark.usefixtures('in_resolve_tests_directory', 'invalidate_caches')


@contextmanager
def sources_root(root):
    root = os.path.abspath(root)
    core.SRC_ROOTS.insert(0, root)
    old_cwd = os.getcwd()
    os.chdir(root)
    try:
        yield
    finally:
        os.chdir(old_cwd)
        core.SRC_ROOTS.remove(root)


def assert_resolved(target_module, local_name, real_name):
    module = core.index_module_by_path(target_module)
    assert module is not None
    resolved = core.resolve_name(local_name, module, core.ClassDefinition)
    assert resolved is not None
    assert resolved.qname == real_name


def test_no_import():
    with sources_root('local/no_import/'):
        assert_resolved('main.py', 'B', 'main.B')


def test_plain_import():
    with sources_root('local/plain_import/'):
        assert_resolved('no_alias.py', 'module.B', 'module.B')
        assert_resolved('with_alias.py', 'alias.B', 'module.B')


def test_import_from_absolute_module():
    with sources_root('local/import_from/absolute/import_module'):
        assert_resolved('no_alias.py', 'module.B', 'package.module.B')
        assert_resolved('with_alias.py', 'alias.B', 'package.module.B')


def test_import_from_absolute_name():
    with sources_root('local/import_from/absolute/import_name'):
        assert_resolved('no_alias.py', 'B', 'module.B')
        assert_resolved('with_alias.py', 'Alias', 'module.B')


def test_import_from_absolute_star():
    with sources_root('local/import_from/absolute/import_star'):
        assert_resolved('main.py', 'B', 'module.B')


def test_import_from_relative_module():
    with sources_root('local/import_from/relative/import_module'):
        assert_resolved('p1/p2/no_alias.py', 'module.B', 'p1.module.B')
        assert_resolved('p1/p2/with_alias.py', 'alias.B', 'p1.module.B')


def test_import_from_relative_name():
    with sources_root('local/import_from/relative/import_name'):
        assert_resolved('p1/p2/no_alias.py', 'B', 'p1.module.B')
        assert_resolved('p1/p2/with_alias.py', 'Alias', 'p1.module.B')


def test_import_from_relative_star():
    with sources_root('local/import_from/relative/import_star'):
        assert_resolved('p1/p2/main.py', 'B', 'p1.module.B')

def test_resolve_stdlib():
    core.index_builtins()
    assert_resolved('stdlib.py', 'datetime', 'datetime.datetime')
    assert_resolved('stdlib.py', 'ArgumentParser', 'argparse.ArgumentParser')
    assert_resolved('stdlib.py', 'RuntimeError', core.BUILTINS + '.RuntimeError')
    assert_resolved('stdlib.py', 'collections.defaultdict', '_collections.defaultdict')
    assert_resolved('stdlib.py', 'dict', core.BUILTINS + '.dict')



