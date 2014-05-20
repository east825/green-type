from conftest import *

TEST_DATA_DIR = 'resolve'

pytestmark = pytest.mark.usefixtures('in_test_data_dir', 'invalidate_caches')


def assert_resolved(target_module, local_name, real_name):
    module = core.index_module_by_path(target_module)
    assert module is not None
    resolved = core.resolve_name(local_name, module, core.ClassDefinition)
    assert resolved is not None
    assert resolved.qname == real_name


def test_no_import():
    with sources_roots('local/no_import/'):
        assert_resolved('main.py', 'B', 'main.B')


def test_plain_import():
    with sources_roots('local/plain_import/'):
        assert_resolved('no_alias.py', 'module.B', 'module.B')
        assert_resolved('with_alias.py', 'alias.B', 'module.B')


def test_import_from_absolute_module():
    with sources_roots('local/import_from/absolute/import_module'):
        assert_resolved('no_alias.py', 'module.B', 'package.module.B')
        assert_resolved('with_alias.py', 'alias.B', 'package.module.B')


def test_import_from_absolute_name():
    with sources_roots('local/import_from/absolute/import_name'):
        assert_resolved('no_alias.py', 'B', 'module.B')
        assert_resolved('with_alias.py', 'Alias', 'module.B')


def test_import_from_absolute_star():
    with sources_roots('local/import_from/absolute/import_star'):
        assert_resolved('main.py', 'B', 'module.B')


def test_import_from_relative_module():
    with sources_roots('local/import_from/relative/import_module'):
        assert_resolved('p1/p2/no_alias.py', 'module.B', 'p1.module.B')
        assert_resolved('p1/p2/with_alias.py', 'alias.B', 'p1.module.B')


def test_import_from_relative_name():
    with sources_roots('local/import_from/relative/import_name'):
        assert_resolved('p1/p2/no_alias.py', 'B', 'p1.module.B')
        assert_resolved('p1/p2/with_alias.py', 'Alias', 'p1.module.B')


def test_import_from_relative_star():
    with sources_roots('local/import_from/relative/import_star'):
        assert_resolved('p1/p2/main.py', 'B', 'p1.module.B')

def test_import_chain():
    with sources_roots('local/import_chain'):
        assert_resolved('main.py', 'alias.A.Inner', 'package.module.MyClass.Inner')


def test_path_to_module():
    with sources_roots('roots',
                       'roots/a',
                       'roots/a/b',
                       'roots/a/b/package',
                       'roots/a/b/package/subpackage'):
        m1 = core.index_module_by_path('a/b/package/subpackage/module.py')
        assert m1 is not None
        assert m1.qname == 'package.subpackage.module'

        with pytest.raises(ValueError):
            core.path_to_module('a/b/package/dir/module.py')

        m2 = core.index_module_by_path('a/b/package/dir/module.py')
        assert m2 is None




def test_resolve_stdlib():
    core.index_builtins()
    with sources_roots():
        assert_resolved('stdlib.py', 'datetime', 'datetime.datetime')
        assert_resolved('stdlib.py', 'ArgumentParser', 'argparse.ArgumentParser')
        assert_resolved('stdlib.py', 'RuntimeError', core.BUILTINS + '.RuntimeError')
        assert_resolved('stdlib.py', 'collections.defaultdict', '_collections.defaultdict')
        assert_resolved('stdlib.py', 'dict', core.BUILTINS + '.dict')



