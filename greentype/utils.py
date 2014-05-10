from collections.abc import Iterable
import ast
import os
import sys


def is_collection(x):
    return isinstance(x, Iterable) and not isinstance(x, (str, bytes))


def partition_any(s, separators, from_end=False):
    for sep in separators:
        if from_end:
            right, _, left = s.rparition(sep)
            if right is not None:
                return right, left
        else:
            right, _, left = s.partition(sep)
            if left is not None:
                return right, left
    return (None, s) if from_end else (s, None)


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
    from greentype.runner import _src_roots

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