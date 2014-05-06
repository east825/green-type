from greentype import utils

def test_camel_to_snake():
    assert '' == utils.camel_to_snake('')
    assert 'foo' == utils.camel_to_snake('FOO')
    assert 'foo_bar' == utils.camel_to_snake('fooBar')
    assert 'foo_bar' == utils.camel_to_snake('FooBar')
    assert 'foo_bar' == utils.camel_to_snake('FOoBar')
    assert 'foo_bar' == utils.camel_to_snake('_foo___bar_')
    assert '' == utils.camel_to_snake('___')
