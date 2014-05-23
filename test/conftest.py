from contextlib import contextmanager
import logging
import os
import pytest
from greentype import core

core.TEST_MODE = True
core.LOG.setLevel(logging.DEBUG)

TEST_ROOT = os.path.dirname(__file__)
TEST_DATA_ROOT = os.path.join(TEST_ROOT, 'test_data')


class TestAnalyzer(core.GreenTypeAnalyzer):

    def __init__(self, project_root, source_roots=None):
        super(TestAnalyzer, self).__init__(project_root, source_roots)
        self.config['FOLLOW_IMPORTS'] = False

    def assert_resolved(self, target_module, local_name, real_name):
        module = self.index_module(path=target_module)
        assert module is not None
        resolved = self.resolve_name(local_name, module)
        assert resolved is not None
        assert resolved.qname == real_name

    @contextmanager
    def roots(self, *roots):
        if not roots:
            roots = [os.getcwd()]
        old_roots = self.config['SOURCE_ROOTS']
        self.config['SOURCE_ROOTS'] = list(map(os.path.abspath, roots))
        old_cwd = os.getcwd()
        os.chdir(roots[0])
        try:
            yield
        finally:
            os.chdir(old_cwd)
            self.config['SOURCE_ROOTS'] = old_roots


@pytest.fixture()
def analyzer(request):
    test_data_dir = getattr(request.module, 'TEST_DATA_DIR', None)
    if test_data_dir:
        os.chdir(os.path.join(TEST_DATA_ROOT, test_data_dir))
    else:
        os.chdir(TEST_DATA_ROOT)
    return TestAnalyzer(os.getcwd())



