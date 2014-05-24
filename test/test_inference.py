TEST_DATA_DIR = 'inference'

from greentype.utils import PY2
from greentype.core import BUILTINS


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
        BUILTINS + '.dict',
        BUILTINS + '.set'
    })
    analyzer.assert_inferred('builtins.check_collections.y', {BUILTINS + '.list',})

    if PY2:
        analyzer.assert_inferred('builtins.check_strings.x', {
            BUILTINS + '.unicode',
            BUILTINS + '.str',
            BUILTINS + '.bytearray'
        })
    else:
        analyzer.assert_inferred('builtins.check_strings.x', {
            BUILTINS + '.str',
            BUILTINS + '.bytes',
            BUILTINS + '.bytearray'
        })

    if PY2:
        analyzer.assert_inferred('builtins.check_strings.y', {
            BUILTINS + '.unicode',
            BUILTINS + '.str'
        })
    else:
        analyzer.assert_inferred('builtins.check_strings.y', {BUILTINS + '.str'})

