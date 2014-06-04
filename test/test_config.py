import os
from conftest import TestAnalyzer
from greentype.core import Config

TEST_DATA_DIR = 'config'


def test_project_config_discovery():
    analyzer = TestAnalyzer('project/src1/module1.py')
    assert analyzer.project_name == 'config-test'
    assert 'SOME_PARAM' not in analyzer.config
    assert analyzer.project_root == os.path.abspath('project')
    assert analyzer.source_roots == [analyzer.project_root,
                                     os.path.abspath('project/src1'),
                                     os.path.abspath('project/src2')]

def test_config_merging():
    conf = Config({
        'PATHS': [],
        'NUMBER': 0,
        'NAME': 'foo',
        'UNDEFINED': None,
    }, 'custom')

    assert conf['PATHS'] == []
    assert conf['NUMBER'] == 0
    assert conf['NAME'] == 'foo'
    assert conf['UNDEFINED'] is None

    conf.update_from_cfg_file('merging/conf1.ini')

    assert conf['PATHS'] == ['path1', 'path2']
    assert conf['NUMBER'] == 0
    assert conf['NAME'] == 'bar'
    assert conf['UNDEFINED'] == 'spam'

    conf.update_from_cfg_file('merging/conf2.ini')

    assert conf['PATHS'] == ['path1', 'path2', 'path3']
    assert conf['NUMBER'] == 42
    assert conf['NAME'] == 'bar'
    assert conf['UNDEFINED'] == 'ham'