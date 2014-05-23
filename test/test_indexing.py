TEST_DATA_DIR = 'indexing'

def test_self_filtering(analyzer):
    module = analyzer.index_module('self_filtering.py')
    assert module is not None

    index = analyzer.indexes['PARAMETER_INDEX']

    # first parameter is not omitted for top-level functions
    assert 'self_filtering.func.self' in index
    assert 'self_filtering.func.x' in index

    # but omitted for normal class methods
    assert 'self_filtering.MyClass.method.self' not in index
    assert 'self_filtering.MyClass.method.x' in index

    # class definition should be immediate scope parent
    assert 'self_filtering.MyClass.method.helper.self' in index
    assert 'self_filtering.MyClass.method.helper.x' in index

    # first parameter is included however if method is annotated with
    # for @classmethod or @staticmethod (but no aliasing check yet)
    assert 'self_filtering.MyClass.class_method.self' in index
    assert 'self_filtering.MyClass.class_method.x' in index

    assert 'self_filtering.MyClass.static_method.self' in index
    assert 'self_filtering.MyClass.static_method.x' in index



