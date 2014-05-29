class D(object):
    pass


class B(D):
    pass


class C(D):
    pass


class A(B, C):
    def foo(self):
        pass

    def bar(self):
        pass


def func(x):
    x.foo()
    x.bar()

