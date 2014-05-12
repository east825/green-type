import module

class A(module.B):
    def foo(self):
        pass

def func(x):
    x.foo()
    x.bar()