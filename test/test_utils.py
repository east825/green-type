import time
import sys

from greentype import utils
from greentype.utils import PY2

if PY2:
    from StringIO import StringIO
else:
    from io import StringIO

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

def test_timed():
    stream = StringIO()
    old_stdout = stream
    sys.stdout = old_stdout
    try:
        # use case #1: decorator with custom message
        @utils.timed_function(msg='msg #1')
        def func(n):
            time.sleep(n)

        func(0.1)

        # use case #2: decorator with standard message
        @utils.timed_function
        def func(n):
            time.sleep(n)

        func(0.1)

        # use case #3: pass both header and function
        utils.timed_function(time.sleep, 'msg #3')(0.1)

        # use case #4: context manager
        with utils.timed(msg='msg #4'):
            time.sleep(0.1)

        # use case #5: supplied callable and arguments
        utils.timed('msg #5', time.sleep, (0.1,))

        lines = sys.stdout.getvalue().splitlines()
        assert lines[0] == 'msg #1: 0.10s'
        assert lines[1] == 'Total: 0.10s'
        assert lines[2] == 'msg #3: 0.10s'
        assert lines[3] == 'msg #4: 0.10s'
        assert lines[4] == 'msg #5: 0.10s'

    finally:
        sys.stdout = old_stdout

