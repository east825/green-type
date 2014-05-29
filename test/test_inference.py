import os
import conftest
from greentype.utils import PY2
from greentype.compat import BUILTINS_NAME

TEST_DATA_DIR = 'inference'


def test_inheritance(analyzer):
    analyzer.index_module('inheritance.py')
    analyzer.assert_inferred('inheritance.func.x', {'inheritance.A'})
    analyzer.assert_inferred('inheritance.func.y', {'inheritance.C', 'inheritance.D'})
    analyzer.assert_inferred('inheritance.func.z', {'inheritance.D'})


def test_builtins(analyzer):
    analyzer.index_builtins()
    analyzer.index_module('builtins.py')

    analyzer.assert_inferred('builtins.check_collections.x', {
        BUILTINS_NAME + '.dict',
        BUILTINS_NAME + '.set'
    })
    analyzer.assert_inferred('builtins.check_collections.y', {BUILTINS_NAME + '.list', })

    if PY2:
        analyzer.assert_inferred('builtins.check_strings.x', {
            BUILTINS_NAME + '.unicode',
            BUILTINS_NAME + '.str',
            BUILTINS_NAME + '.bytearray'
        })
    else:
        analyzer.assert_inferred('builtins.check_strings.x', {
            BUILTINS_NAME + '.str',
            BUILTINS_NAME + '.bytes',
            BUILTINS_NAME + '.bytearray'
        })

    if PY2:
        analyzer.assert_inferred('builtins.check_strings.y', {
            BUILTINS_NAME + '.unicode',
            BUILTINS_NAME + '.str'
        })
    else:
        analyzer.assert_inferred('builtins.check_strings.y', {BUILTINS_NAME + '.str'})


def test_diamonds():
    def check(module_name, classes):
        analyzer = conftest.TestAnalyzer(os.getcwd())
        analyzer.index_module(name=module_name)
        analyzer.assert_inferred(module_name + '.func.x', classes)

    check('diamond_top', {'diamond_top.D'})
    check('diamond_bottom', {'diamond_bottom.A'})
    check('diamond_siblings', {'diamond_siblings.B', 'diamond_siblings.C'})
    check('diamond_left', {'diamond_left.B'})
    check('diamond_disjointed', {'diamond_disjointed.B', 'diamond_disjointed.D'})