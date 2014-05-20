from contextlib import contextmanager
import logging
import os
import pytest
from greentype import core

core.TEST_MODE = True
core.LOG.setLevel(logging.DEBUG)

TEST_ROOT = os.path.dirname(__file__)
TEST_DATA_ROOT = os.path.join(TEST_ROOT, 'test_data')


@pytest.fixture()
def in_test_data_dir(request):
    test_data_dir = getattr(request.module, 'TEST_DATA_DIR', None)
    if test_data_dir:
        os.chdir(os.path.join(TEST_DATA_ROOT, test_data_dir))
    else:
        os.chdir(TEST_DATA_ROOT)


@pytest.fixture()
def invalidate_caches():
    core.Indexer.CLASS_INDEX.clear()
    core.Indexer.CLASS_ATTRIBUTE_INDEX.clear()
    core.Indexer.FUNCTION_INDEX.clear()
    core.Indexer.PARAMETERS_INDEX.clear()
    core.Indexer.MODULE_INDEX.clear()


@contextmanager
def sources_root(root=None):
    if root is None:
        root = os.getcwd()
    root = os.path.abspath(root)
    core.SRC_ROOTS.insert(0, root)
    old_cwd = os.getcwd()
    os.chdir(root)
    try:
        yield
    finally:
        os.chdir(old_cwd)
        core.SRC_ROOTS.remove(root)
