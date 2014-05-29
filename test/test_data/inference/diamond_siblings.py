class D(object):
    def bar(self):
        pass


class B(D):
    def foo(self):
        pass


class C(D):
    def foo(self):
        pass

    def bar(self):
        pass


class A(B, C):
    def foo(self):
        pass

    def bar(self):
        pass


def func(x):
    x.foo()
    x.bar()

