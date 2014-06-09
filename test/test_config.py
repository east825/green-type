import os
from conftest import TestAnalyzer
from greentype.core import Config

TEST_DATA_DIR = 'config'


def test_project_config():

    def abs_path(path):
        return os.path.abspath(path)

    def project_path(analyzer, path):
        if not os.path.isabs(path):
            return os.path.normpath(os.path.join(analyzer.project_root, path))
        return path

    analyzer = TestAnalyzer('project/src1/module1.py')
    analyzer.discover_project_config()
    assert analyzer.project_name == 'config-test'
    assert 'SOME_PARAM' not in analyzer.config
    assert analyzer.project_root == abs_path('project')
    assert analyzer.source_roots == [analyzer.project_root,
                                     abs_path('project/src1'),
                                     abs_path('project/src2')]

    assert analyzer.excluded == [project_path(analyzer, 'excluded'),
                                 project_path(analyzer, 'excluded/included/excluded_explicitly.py')]
    assert analyzer.included == [project_path(analyzer, 'excluded/included')]

    assert analyzer.is_inside_project('project/excluded/included/module.py')
    assert analyzer.is_inside_project(project_path(analyzer, 'excluded/included/module.py'))

    # included files checked first
    assert analyzer.is_inside_project('project/excluded/included/excluded_explicitly.py')
    assert analyzer.is_inside_project('project/src1/module1.py')
    assert analyzer.is_inside_project('project/greentype.cfg')

    assert not analyzer.is_inside_project('project/excluded/module.py')
    assert not analyzer.is_inside_project('project/excluded')

    assert analyzer.config['BUILTINS'][-2:] == ['audioop', 'ssl']


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