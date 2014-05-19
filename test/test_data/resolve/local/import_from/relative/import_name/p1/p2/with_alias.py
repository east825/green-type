from ..module import B as Alias

class A(Alias):
    def foo(self):
        pass

def func(x):
    x.foo()
    x.bar()