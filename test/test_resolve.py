from contextlib import contextmanager
from greentype import core
from greentype import utils
import os
import pytest
from common import *


pytestmark = pytest.mark.usefixtures('in_tests_directory', 'invalidate_caches')


def assert_resolved(target_module, local_name, real_name):
    module = core.index_module_by_path(target_module)
    assert module is not None
    resolved = core.resolve_name(local_name, module, core.ClassDefinition)
    assert resolved is not None
    assert resolved.qname == real_name


def test_no_import():
    with sources_root('resolve/local/no_import/'):
        assert_resolved('main.py', 'B', 'main.B')


def test_plain_import():
    with sources_root('resolve/local/plain_import/'):
        assert_resolved('no_alias.py', 'module.B', 'module.B')
        assert_resolved('with_alias.py', 'alias.B', 'module.B')


def test_import_from_absolute_module():
    with sources_root('resolve/local/import_from/absolute/import_module'):
        assert_resolved('no_alias.py', 'module.B', 'package.module.B')
        assert_resolved('with_alias.py', 'alias.B', 'package.module.B')


def test_import_from_absolute_name():
    with sources_root('resolve/local/import_from/absolute/import_name'):
        assert_resolved('no_alias.py', 'B', 'module.B')
        assert_resolved('with_alias.py', 'Alias', 'module.B')


def test_import_from_absolute_star():
    with sources_root('resolve/local/import_from/absolute/import_star'):
        assert_resolved('main.py', 'B', 'module.B')


def test_import_from_relative_module():
    with sources_root('resolve/local/import_from/relative/import_module'):
        assert_resolved('p1/p2/no_alias.py', 'module.B', 'p1.module.B')
        assert_resolved('p1/p2/with_alias.py', 'alias.B', 'p1.module.B')


def test_import_from_relative_name():
    with sources_root('resolve/local/import_from/relative/import_name'):
        assert_resolved('p1/p2/no_alias.py', 'B', 'p1.module.B')
        assert_resolved('p1/p2/with_alias.py', 'Alias', 'p1.module.B')


def test_import_from_relative_star():
    with sources_root('resolve/local/import_from/relative/import_star'):
        assert_resolved('p1/p2/main.py', 'B', 'p1.module.B')

def test_resolve_stdlib():
    core.index_builtins()
    assert_resolved('resolve/stdlib.py', 'datetime', 'datetime.datetime')
    assert_resolved('resolve/stdlib.py', 'ArgumentParser', 'argparse.ArgumentParser')
    assert_resolved('resolve/stdlib.py', 'RuntimeError', core.BUILTINS + '.RuntimeError')
    assert_resolved('resolve/stdlib.py', 'collections.defaultdict', '_collections.defaultdict')
    assert_resolved('resolve/stdlib.py', 'dict', core.BUILTINS + '.dict')



