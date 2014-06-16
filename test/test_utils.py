import os
import platform
import time
import pytest

from greentype import utils

from conftest import TEST_ROOT, TEST_DATA_ROOT


def test_camel_to_snake():
    assert utils.camel_to_snake('') == ''
    assert utils.camel_to_snake('FOO') == 'foo'
    assert utils.camel_to_snake('fooBar') == 'foo_bar'
    assert utils.camel_to_snake('FooBar') == 'foo_bar'
    assert utils.camel_to_snake('FOoBar') == 'foo_bar'
    assert utils.camel_to_snake('_foo___bar_') == 'foo_bar'
    assert utils.camel_to_snake('___') == ''


def test_qname():
    assert utils.qname_head('') is None
    assert utils.qname_tail('') is None
    assert utils.qname_head('foo.bar') == 'bar'
    assert utils.qname_tail('foo.bar') == 'foo'

    assert utils.qname_qualified_by('foo.bar', '')
    assert utils.qname_qualified_by('foo.bar', 'foo')
    assert utils.qname_qualified_by('foo.bar', 'foo.bar')
    assert not utils.qname_qualified_by('foo.bar', 'foo.baz')

    assert utils.qname_drop('foo.bar', '') == 'foo.bar'
    assert utils.qname_drop('foo.bar', 'foo') == 'bar'
    assert utils.qname_drop('foo.bar', 'foo.bar') == ''
    assert utils.qname_drop('foo.bar', 'foo.baz') == 'foo.bar'

    assert utils.qname_merge('foo.bar.baz', 'baz.quux') == 'foo.bar.baz.quux'
    assert utils.qname_merge('foo.bar.baz', 'baz.bar') == 'foo.bar.baz.bar'
    assert utils.qname_merge('foo.bar.baz', '') == 'foo.bar.baz'
    assert utils.qname_merge('', 'foo.bar.baz') == 'foo.bar.baz'
    assert utils.qname_merge('', '') == ''
    assert utils.qname_merge('foo', 'foo') == 'foo'
    assert utils.qname_merge('foo', 'foo.bar') == 'foo.bar'
    assert utils.qname_merge('foo.bar', 'foo') == 'foo.bar.foo'
    assert utils.qname_merge('foo.bar', 'foo', accept_disjoint=False) is None

    assert utils.qname_split('foo.bar') == ('foo', 'bar')
    assert utils.qname_split('foo') == (None, 'foo')
    assert utils.qname_split('') == (None, '')

def test_memoized():
    @utils.memoized
    def func(n):
        func.called += 1

    func.called = 0

    func(1)
    func(2)
    func(2)
    assert func.called == 2

    func.clear_results()

    func(1)
    func(2)
    assert func.called == 4

    @utils.memoized(guard_value=None)
    def func():
        return func()

    assert func() is None

    # if function fails, guard value should be removed from cache
    _fail = True
    @utils.memoized(guard_value=10)
    def func():
        func()
        if _fail:
            raise RuntimeError()
        return func() + func()

    with pytest.raises(RuntimeError):
        func()

    _fail = False
    assert func() == 20



def test_timed(capsys):
    # use case #1: decorator with custom message
    @utils.timed_function(msg='msg #1')
    def func(n):
        time.sleep(n)

    func(0.1)
    assert capsys.readouterr()[0] == 'msg #1: 0.10s\n'

    # use case #2: decorator with standard message
    @utils.timed_function
    def func(n):
        time.sleep(n)

    func(0.1)
    assert capsys.readouterr()[0] == 'Total: 0.10s\n'

    # use case #3: pass both header and function
    utils.timed_function(time.sleep, 'msg #3')(0.1)
    assert capsys.readouterr()[0] == 'msg #3: 0.10s\n'

    # use case #4: context manager
    with utils.timed(msg='msg #4'):
        time.sleep(0.1)
    assert capsys.readouterr()[0] == 'msg #4: 0.10s\n'

    # use case #5: supplied callable and arguments
    utils.timed('msg #5', time.sleep, (0.1,))
    assert capsys.readouterr()[0] == 'msg #5: 0.10s\n'


def test_parent_directories(tmpdir):
    def parents(start, stop, strict):
        return list(utils.parent_directories(start, stop, strict))

    # root corner-cases
    if platform.system() == 'Windows':
        root_path = os.path.splitdrive(tmpdir.strpath)[0] + '\\'
    else:
        root_path = '/'

    assert parents(root_path, None, False) == [root_path]
    assert parents(root_path, None, True) == []
    assert parents(root_path, root_path, False) == []
    assert parents(root_path, root_path, True) == []

    stop_at = tmpdir.strpath
    file = tmpdir.ensure('foo/bar/baz/file.txt')
    assert file.check()

    foo_path = tmpdir.join('foo').strpath
    bar_path = tmpdir.join('foo/bar').strpath
    baz_path = tmpdir.join('foo/bar/baz').strpath
    file_path = file.strpath

    # strict parameter doesn't matter when start is a file
    assert parents(file_path, stop_at, False) == [baz_path, bar_path, foo_path]
    assert parents(file_path, stop_at, True) == [baz_path, bar_path, foo_path]

    # but does when it's a directory
    assert parents(baz_path, stop_at, False) == [baz_path, bar_path, foo_path]
    assert parents(baz_path, stop_at, True) == [bar_path, foo_path]

    # a couple of tests outside of temp dir
    assert list(utils.parent_directories(TEST_DATA_ROOT, TEST_ROOT, False)) == [TEST_DATA_ROOT]
    assert list(utils.parent_directories(TEST_DATA_ROOT, TEST_ROOT, True)) == []

    assert list(utils.parent_directories(__file__, TEST_ROOT, False)) == []
    assert list(utils.parent_directories(__file__, TEST_ROOT, True)) == []


def test_dict_merge():
    assert utils.dict_merge(
        {
            'foo': {1, 2},
            'bar': frozenset('ab'),
            'baz': [1, None, 'ham'],
            'quux': {'key': 'identical'}
        }, {
            'foo': {3},
            'bar': frozenset('c'),
            'baz': ['spam'],
            'quux': {'key': 'identical'}
        }) == {
               'foo': {1, 2, 3},
               'bar': frozenset('abc'),
               'baz': [1, None, 'ham', 'spam'],
               'quux': {'key': 'identical'}
           }

    assert utils.dict_merge({'foo': None}, {'foo': 42}, override_none=True) == {'foo': 42}
    assert utils.dict_merge({'foo': None}, {'foo': 42}, override=True) == {'foo': 42}
    assert utils.dict_merge({}, {'foo': 42}, add_new=False, silent=True) == {}

    with pytest.raises(ValueError):
        utils.dict_merge({}, {'foo': 42}, add_new=False)

    with pytest.raises(ValueError):
        utils.dict_merge({'foo': 42}, {'foo': ()})


def test_deep_filter():
    assert utils.deep_filter(lambda x: not isinstance(x, list) or x, {
        'foo': [],
        'bar': ['baz', []]
    }) == {'bar': ['baz']}

    assert utils.deep_filter(lambda x: x is not utils.MISSING, {
        'foo': utils.MISSING,
        'bar': [None, 42, 'spam', utils.MISSING],
        'baz': {utils.MISSING},
        'quux': frozenset([utils.MISSING, utils.MISSING, frozenset([utils.MISSING])])
    }) == {'bar': [None, 42, 'spam'], 'baz': set(), 'quux': frozenset([frozenset()])}

    assert utils.deep_filter(None, {'foo': None, 'bar': [None, None, 42]}) == {'bar': [42]}



