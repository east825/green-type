from module_b import B

class A(B):
    def foo(self):
        pass

def func(x):
    x.foo()
    x.bar()