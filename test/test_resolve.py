from conftest import *

TEST_DATA_DIR = 'resolve'

def test_no_import(analyzer):
    with analyzer.roots('local/no_import/'):
        analyzer.assert_resolved('main.py', 'B', 'main.B')


def test_plain_import(analyzer):
    with analyzer.roots('local/plain_import/'):
        analyzer.assert_resolved('no_alias.py', 'module.B', 'module.B')
        analyzer.assert_resolved('with_alias.py', 'alias.B', 'module.B')


def test_import_from_absolute_module(analyzer):
    with analyzer.roots('local/import_from/absolute/import_module'):
        analyzer.assert_resolved('no_alias.py', 'module.B', 'package.module.B')
        analyzer.assert_resolved('with_alias.py', 'alias.B', 'package.module.B')


def test_import_from_absolute_name(analyzer):
    with analyzer.roots('local/import_from/absolute/import_name'):
        analyzer.assert_resolved('no_alias.py', 'B', 'module.B')
        analyzer.assert_resolved('with_alias.py', 'Alias', 'module.B')


def test_import_from_absolute_star(analyzer):
    with analyzer.roots('local/import_from/absolute/import_star'):
        analyzer.assert_resolved('main.py', 'B', 'module.B')


def test_import_from_relative_module(analyzer):
    with analyzer.roots('local/import_from/relative/import_module'):
        analyzer.assert_resolved('p1/p2/no_alias.py', 'module.B', 'p1.module.B')
        analyzer.assert_resolved('p1/p2/with_alias.py', 'alias.B', 'p1.module.B')


def test_import_from_relative_name(analyzer):
    with analyzer.roots('local/import_from/relative/import_name'):
        analyzer.assert_resolved('p1/p2/no_alias.py', 'B', 'p1.module.B')
        analyzer.assert_resolved('p1/p2/with_alias.py', 'Alias', 'p1.module.B')


def test_import_from_relative_star(analyzer):
    with analyzer.roots('local/import_from/relative/import_star'):
        analyzer.assert_resolved('p1/p2/main.py', 'B', 'p1.module.B')

def test_import_chain(analyzer):
    with analyzer.roots('local/import_chain'):
        analyzer.assert_resolved('main.py', 'alias.A.Inner', 'package.module.MyClass.Inner')

def test_import_chain2(analyzer):
    with analyzer.roots('local/import_chain2'):
        analyzer.assert_resolved('main.py', 'module.A', 'package.sibling.A')


def test_path_to_module(analyzer):
    with analyzer.roots('roots',
                       'roots/a',
                       'roots/a/b',
                       'roots/a/b/package',
                       'roots/a/b/package/subpackage'):
        m1 = analyzer.index_module('a/b/package/subpackage/module.py')
        assert m1 is not None
        assert m1.qname == 'package.subpackage.module'

        with pytest.raises(ValueError):
            analyzer.path_to_module_name('a/b/package/dir/module.py')

        m2 = analyzer.index_module('a/b/package/dir/module.py')
        assert m2 is None


def test_resolve_stdlib(analyzer):
    analyzer.index_builtins()
    analyzer.assert_resolved('stdlib.py', 'datetime', 'datetime.datetime')
    analyzer.assert_resolved('stdlib.py', 'ArgumentParser', 'argparse.ArgumentParser')
    analyzer.assert_resolved('stdlib.py', 'RuntimeError', core.BUILTINS + '.RuntimeError')
    analyzer.assert_resolved('stdlib.py', 'collections.defaultdict', '_collections.defaultdict')
    analyzer.assert_resolved('stdlib.py', 'dict', core.BUILTINS + '.dict')



