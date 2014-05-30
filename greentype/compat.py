from __future__ import print_function, division, unicode_literals

# TODO: consider using python-future instead
# TODO: use Travis to automate testing on multiple Python versions

import sys

PY2 = sys.version_info.major == 2

if PY2:
    import io

    open = io.open

    # noinspection PyUnresolvedReferences
    import collections as collections_abc

    BUILTINS_NAME = '__builtin__'

else:
    open = open

    # noinspection PyUnresolvedReferences
    import collections.abc as collections_abc

    BUILTINS_NAME = 'builtins'

import textwrap

if not hasattr(textwrap, 'indent'):
    def indent(s, prefix):
        lines = s.splitlines(True)
        return ''.join(prefix + line for line in lines)
else:
    indent = lambda s, prefix: textwrap.indent(s, prefix)
