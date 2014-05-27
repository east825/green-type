from __future__ import unicode_literals, print_function

import functools
import os
import contextlib
import timeit
import traceback

from .compat import collections_abc, PY2


def is_collection(x):
    if not isinstance(x, collections_abc.Iterable):
        return False
    return not isinstance(x, basestring) if PY2 else not isinstance(x, (str, bytes))


def partition_any(s, separators, from_end=False):
    for sep in separators:
        if from_end:
            right, _, left = s.rpartition(sep)
            if right:
                return right, left
        else:
            right, _, left = s.partition(sep)
            if left:
                return right, left
    return (None, s) if from_end else (s, None)


def qname_merge(n1, n2, accept_disjoint=True):
    # Do not use sep='.' for Python 2.x compatibility!
    parts1 = n1.split('.')
    parts2 = n2.split('.')
    if not n1 or not n2:
        return n2 or n1
    for n in range(len(parts2), 0, -1):
        if parts1[-n:] == parts2[:n]:
            return '.'.join(parts1 + parts2[n:])
    return '.'.join(parts1 + parts2) if accept_disjoint else None


def qname_head(name):
    _, _, head = name.rpartition('.')
    return head or None


def qname_tail(name):
    tail, _, _ = name.rpartition('.')
    return tail or None


def qname_split(name):
    tail, _, head = name.rpartition('.')
    return tail or None, head


def qname_drop(name, qualifier):
    if qname_qualified_by(name, qualifier) and qualifier:
        return name[len(qualifier + '.'):]
    return name


def qname_qualified_by(name, qualifier):
    if not qualifier:
        return True
    # parts1 = name.split('.')
    # parts2 = qualifier.split('.')
    # return parts1[:len(parts2)] == parts2
    return name == qualifier or name.startswith(qualifier + '.')


def method_decorator(decorator):
    def new_decorator(f):
        @functools.wraps(f)
        def wrapper(self, *args, **kwargs):
            bounded = functools.partial(f, self)
            functools.update_wrapper(bounded, f)
            return decorator(bounded)(*args, **kwargs)

        return wrapper

    return new_decorator


def memoized(f):
    results = {}
    missing = object()

    @functools.wraps(f)
    def wrapper(*args):
        r = results.get(args, missing)
        if r is missing:
            r = results[args] = f(*args)
        return r

    return wrapper


def timed(msg=None, func=None, args=None, kwargs=None):
    class Timer(object):
        def __enter__(self):
            self.start = timeit.default_timer()
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            elapsed = timeit.default_timer() - self.start
            print('{}: {:.2f}s'.format(msg or 'Total', elapsed))

    if func is not None:
        with Timer():
            func(*(args or ()), **(kwargs or {}))
    else:
        return Timer()


def timed_function(func=None, msg=None):
    if func is None and msg:
        return functools.partial(timed_function, msg=msg)
    if func:
        def wrapper(*args, **kwargs):
            with timed(msg):
                return func(*args, **kwargs)

        return wrapper
    raise ValueError('Either function or header should be specified')


def camel_to_snake(s):
    """Translate CamelCase identifier to snake_case.

    If identifier is already in snake case it will be returned unchanged,
    except that leading and trailing underscores will be stripped.
    """
    words = []
    word = []
    prev_upper = False
    for c in s:
        if ((c.isupper() and not prev_upper) or not c.isalnum()) and word:
            words.append(''.join(word))
            word = []
        if c.isalnum():
            word.append(c.lower())
            prev_upper = c.isupper()
    if word:
        words.append(''.join(word))
    return '_'.join(words)


def is_python_source_module(path):
    _, ext = os.path.splitext(path)
    # importlib.machinery.SOURCE_SUFFIXES?
    return os.path.isfile(path) and ext == '.py'


@contextlib.contextmanager
def suppress_exceptions():
    try:
        yield
    except Exception:
        traceback.print_exc()


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