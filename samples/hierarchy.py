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
        x = self.foo + 42
        if not self:
            pass
        function(self)
        pass


def function(x):
    x.foo() # A, C
    x.bar()
    x.pop()


