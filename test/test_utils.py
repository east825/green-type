import platform
import time

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

def test_parent_directories():
    if platform.system() == 'Linux':
        path = '/foo/bar/baz'
        assert list(utils.parent_directories(path)) == ['/foo/bar', '/foo', '/']
        # such structure actually doesn't exists
        assert list(utils.parent_directories(path, strict=False)) == \
               ['/foo/bar', '/foo', '/']
        assert list(utils.parent_directories(path, stop=path)) == []
        assert list(utils.parent_directories(path, '/foo/', True)) == ['/foo/bar']
        # assert list(utils.parent_directories(path, '/foo/', False)) == ['/foo/bar/baz', '/foo/bar']
        assert list(utils.parent_directories('/', strict=True)) == []
        assert list(utils.parent_directories('/', strict=False)) == ['/']

    assert list(utils.parent_directories(TEST_DATA_ROOT, TEST_ROOT, False)) == [TEST_DATA_ROOT]
    assert list(utils.parent_directories(TEST_DATA_ROOT, TEST_ROOT, True)) == []

    assert list(utils.parent_directories(__file__, TEST_ROOT, False)) == []
    assert list(utils.parent_directories(__file__, TEST_ROOT, True)) == []


