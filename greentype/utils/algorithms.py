import functools


class _Missing(object):
    def __str__(self):
        return '<missing>'

    def __repr__(self):
        return str(self)


MISSING = _Missing()


def memoized(f):
    results = {}

    @functools.wraps(f)
    def wrapper(*args):
        r = results.get(args, MISSING)
        if r is MISSING:
            r = results[args] = f(*args)
        return r

    return wrapper


def dict_merge(d1, d2, add_new=True, override=False, override_none=False, silent=False):
    # TODO: cycles detection
    copy = d1.copy()
    for key, value in d2.items():
        if key not in d1:
            if add_new:
                copy[key] = value
            elif not silent:
                raise ValueError('Addition of new keys is not allowed: '
                                 'key={!r} value={!r}'.format(key, value))
        elif isinstance(d1[key], list) and isinstance(value, list):
            copy[key] = d1[key] + value
        elif isinstance(d1[key], set) and isinstance(value, set):
            copy[key] = d1[key] | value
        elif isinstance(d1[key], frozenset) and isinstance(value, frozenset):
            copy[key] = d1[key] | value
        elif isinstance(d1[key], dict) and isinstance(value, dict):
            copy[key] = dict_merge(d1[key], value, add_new, override, override_none, silent)
        elif d1[key] == value:
            pass
        elif override or (d1[key] is None and override_none):
            copy[key] = value
        elif not silent:
            raise ValueError("Cannot merge values: key={!r},"
                             "values={!r} and {!r}".format(d1[key], value, key))
    return copy


def deep_filter(func, d):
    if func is None:
        func = lambda x: x is not None

    def helper(obj):
        if isinstance(obj, dict):
            return {k: helper(v) for k, v in obj.items() if func(v)}
        elif isinstance(obj, list):
            return [helper(v) for v in obj if func(v)]
        elif isinstance(obj, set):
            return {helper(v) for v in obj if func(v)}
        elif isinstance(obj, frozenset):
            return frozenset(helper(v) for v in obj if func(v))
        return obj

    return helper(d)
