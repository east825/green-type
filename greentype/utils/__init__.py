from __future__ import unicode_literals, print_function

import contextlib
import timeit
import traceback

from ..compat import collections_abc, PY2
from .strings import *
from .algorithms import *
from .paths import *


def is_collection(x):
    if not isinstance(x, collections_abc.Iterable):
        return False
    return not isinstance(x, basestring) if PY2 else not isinstance(x, (str, bytes))


def method_decorator(decorator):
    def new_decorator(f):
        @functools.wraps(f)
        def wrapper(self, *args, **kwargs):
            bounded = functools.partial(f, self)
            functools.update_wrapper(bounded, f)
            return decorator(bounded)(*args, **kwargs)

        return wrapper

    return new_decorator


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


@contextlib.contextmanager
def suppress_exceptions():
    try:
        yield
    except Exception:
        traceback.print_exc()