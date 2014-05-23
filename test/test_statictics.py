from conftest import *

TEST_DATA_DIR = 'statistics'

def test_usages(analyzer):
    module = analyzer.index_module('usages.py')
    assert module is not None

    params = analyzer.indexes['PARAMETER_INDEX']

    x1 = params['usages.func1.x']
    assert x1.used_directly == 3
    assert x1.used_as_argument == 0
    assert x1.used_as_operand == 1
    assert x1.returned == 2

    x2 = params['usages.func2.x']
    assert x2.used_directly == 4
    assert x2.used_as_argument == 0
    assert x2.used_as_operand == 4
    assert x2.returned == 0

    x2 = params['usages.func2.x']
    assert x2.used_directly == 4
    assert x2.used_as_argument == 0
    assert x2.used_as_operand == 4
    assert x2.returned == 0

    x3 = params['usages.func3.x']
    assert x3.used_directly == 3
    assert x3.used_as_argument == 2
    assert x3.used_as_operand == 1
    assert x3.returned == 0
