class A(object):
    def foo(self):
        pass


class B(A):
    def bar(self):
        pass


class C(B, A):
    def baz(self):
        pass


class D(dict):
    def baz(self):
        pass

    def bar(self):
        pass

    def quux(self):
        pass


def func(x, y, z):
    x.foo()

    y.bar()
    y.baz()

    z.quux()

