import os


def parent_directories(start, stop=None, strict=True):
    """Iterates over parent directories of specified path.

    If strict is False and start path points to directory, it will be
    returned as well, unless stop is specified and start == stop.
    Stop directory is always excluded from results.

    If start is '/' or drive root on Windows, it will be returned only if
    strict == False.
    """
    start = os.path.abspath(start)
    if stop is not None:
        stop = os.path.abspath(stop)

    if start == stop:
        return

    if not strict and os.path.isdir(start):
        yield start

    while True:
        parent = os.path.dirname(start)
        if parent == stop or parent == start:
            break
        yield parent
        start = parent


def is_python_source_module(path):
    _, ext = os.path.splitext(path)
    # importlib.machinery.SOURCE_SUFFIXES?
    return os.path.isfile(path) and ext == '.py'
