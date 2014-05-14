from contextlib import contextmanager
import os
import pytest
from greentype import core

core.TEST_MODE = True


@pytest.fixture()
def in_tests_directory():
    os.chdir(os.path.dirname(__file__))


@pytest.fixture()
def invalidate_caches():
    core.Indexer.CLASS_INDEX.clear()
    core.Indexer.CLASS_ATTRIBUTE_INDEX.clear()
    core.Indexer.FUNCTION_INDEX.clear()
    core.Indexer.PARAMETERS_INDEX.clear()
    core.Indexer.MODULE_INDEX.clear()

@contextmanager
def sources_root(root):
    root = os.path.abspath(root)
    core.SRC_ROOTS.insert(0, root)
    old_cwd = os.getcwd()
    os.chdir(root)
    try:
        yield
    finally:
        os.chdir(old_cwd)
        core.SRC_ROOTS.remove(root)
