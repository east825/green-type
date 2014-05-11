class A(object):
    def foo(self):
        pass
    def bar(self):
        pass


class B(dict):
    def bar(self):
        pass
    def foo(self):
        pass

class C(B):
    def bar(self):
        pass


def function(x):
    x.foo() # A, C
    x.bar()
    x.pop()


