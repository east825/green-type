from .. import module as alias

class A(alias.B):
    def foo(self):
        pass

def func(x):
    x.foo()
    x.bar()