# def func(x):
#     if True:
#         x = 42
#     return x
#
# n = func('foo') # str | int
#
# def func2(x, y, *, z=None, **kwargs):
#     pass
#
# def func2(x, y, z=None, **kwargs):
#     pass
#
# def func(x, y):
#     z = y[42]
#     if True:
#         x.foo()
#     else:
#         y = x
#     y.bar()

def func3(x, y):
    t = x
    x = y
    y = t
    x.foo()
    y.bar

class A(B):
    CONST = 42

    def foo(self):
        pass

