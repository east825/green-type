from greentype import utils

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