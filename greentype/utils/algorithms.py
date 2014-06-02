import functools


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

