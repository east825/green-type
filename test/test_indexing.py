import conftest

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

    # first parameter is included however if method is not
    # annotated with for @staticmethod (but no aliasing check yet)
    assert 'self_filtering.MyClass.class_method.self' not in index
    assert 'self_filtering.MyClass.class_method.x' in index

    assert 'self_filtering.MyClass.static_method.self' in index
    assert 'self_filtering.MyClass.static_method.x' in index

def test_module_exclusion():
    analyzer = conftest.TestAnalyzer('module_exclusion')
    analyzer.config['EXCLUDE'] = ['excluded']
    analyzer.config['INCLUDE'] = ['excluded/included']

    analyzer.index_project()

    assert 'main' in analyzer.indexes['MODULE_INDEX']
    assert 'excluded' not in analyzer.indexes['MODULE_INDEX']
    assert 'excluded.module' not in analyzer.indexes['MODULE_INDEX']
    assert 'excluded.included' in analyzer.indexes['MODULE_INDEX']
    assert 'excluded.included.module' in analyzer.indexes['MODULE_INDEX']

# @pytest.mark.skipif(platform.system() != 'Windows', reason='Windows filesystem required.')
def test_case_insensitive_paths():
    # This can happen on Windows only. Case insensitive file system
    # can cause the same module to be included in indexes twice.
    # See test data for details.
    analyzer = conftest.TestAnalyzer('case_insensitive_paths')
    analyzer.index_project()

    assert 'package.Foo' not in analyzer.indexes['MODULE_INDEX']
    assert 'package.Foo.Foo' not in analyzer.indexes['CLASS_INDEX']







