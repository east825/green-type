from collections.abc import Iterable
import functools
import os
import sys


def is_collection(x):
    return isinstance(x, Iterable) and not isinstance(x, (str, bytes))


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
    parts1 = n1.split(sep='.')
    parts2 = n2.split(sep='.')
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


def qname_qualified_by(name, qualifier):
    if not qualifier:
        return True
    # parts1 = name.split('.')
    # parts2 = qualifier.split('.')
    # return parts1[:len(parts2)] == parts2
    return name == qualifier or name.startswith(qualifier + '.')


def memo(f):
    results = {}
    missing = object()

    @functools.wraps(f)
    def wrapper(*args):
        r = results.get(args, missing)
        if r is missing:
            r = results[args] = f(*args)
        return r

    return wrapper


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


def module_path_to_name(path):
    from runner import _src_roots

    path = os.path.abspath(path)
    for src_root in _src_roots + sys.path:
        if path.startswith(src_root):
            relative = os.path.relpath(path, src_root)
            transformed, _ = os.path.splitext(relative)
            dir_name, base_name = os.path.split(transformed)
            if base_name == '__init__':
                transformed = dir_name
            return transformed.replace(os.path.sep, '.').strip('.')
    raise ValueError('Unresolved module {!r}'.format(path))


def is_python_source_module(path):
    _, ext = os.path.splitext(path)
    # importlib.machinery.SOURCE_SUFFIXES?
    return os.path.isfile(path) and ext == '.py'
