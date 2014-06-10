class Class:
    # excluded from class attributes always
    __doc__ = 'foo'

    # excluded from class attributes on Python 3
    def __init__(self):
        pass

    # included always
    def foo(self):
        pass


def func(x):
    x.foo()
    x.__doc__
    x.__init__()
