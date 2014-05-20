from conftest import *

TEST_DATA_DIR = 'statistics'

pytestmark = pytest.mark.usefixtures('in_test_data_dir', 'invalidate_caches')


def test_usages():
    with sources_roots():
        module = core.index_module_by_path('usages.py')
        assert module is not None

        x1 = core.Indexer.PARAMETERS_INDEX['usages.func1.x']
        assert x1.used_directly == 3
        assert x1.used_as_argument == 0
        assert x1.used_as_operand == 1
        assert x1.returned == 2

        x2 = core.Indexer.PARAMETERS_INDEX['usages.func2.x']
        assert x2.used_directly == 4
        assert x2.used_as_argument == 0
        assert x2.used_as_operand == 4
        assert x2.returned == 0

        x2 = core.Indexer.PARAMETERS_INDEX['usages.func2.x']
        assert x2.used_directly == 4
        assert x2.used_as_argument == 0
        assert x2.used_as_operand == 4
        assert x2.returned == 0

        x3 = core.Indexer.PARAMETERS_INDEX['usages.func3.x']
        assert x3.used_directly == 3
        assert x3.used_as_argument == 2
        assert x3.used_as_operand == 1
        assert x3.returned == 0
