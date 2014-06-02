import os
from conftest import TestAnalyzer

TEST_DATA_DIR = 'config'


def test_config_discovery():
    analyzer = TestAnalyzer('project/src1/module1.py')
    assert analyzer.project_name == 'config-test'
    assert 'SOME_PARAM' not in analyzer.config
    assert analyzer.project_root == os.path.abspath('project')
    assert analyzer.source_roots == [analyzer.project_root,
                                     os.path.abspath('project/src1'),
                                     os.path.abspath('project/src2')]
