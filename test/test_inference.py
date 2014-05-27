TEST_DATA_DIR = 'inference'

from greentype.utils import PY2
from greentype.compat import BUILTINS_NAME


def index_builtins_and_module(analyzer, module_path):
    analyzer.index_builtins()
    analyzer.index_module(module_path)


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
    analyzer.assert_inferred('builtins.check_collections.y', {BUILTINS_NAME + '.list',})

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

