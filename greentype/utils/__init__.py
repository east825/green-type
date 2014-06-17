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


class _Timer(object):
    def __init__(self):
        self.elapsed = 0
        self.start_time = 0

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()

    def start(self):
        self.start_time = timeit.default_timer()

    def stop(self):
        if self.start_time == 0:
            raise Exception('Timer was not started')
        self.elapsed += timeit.default_timer() - self.start_time
        self.start_time = 0

timer = _Timer

@contextlib.contextmanager
def suppress_exceptions():
    try:
        yield
    except Exception:
        traceback.print_exc()