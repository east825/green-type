class D(object):
    def foo(self):
        pass

    def bar(self):
        pass

class B(object):
    def foo(self):
        pass

    def bar(self):
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

