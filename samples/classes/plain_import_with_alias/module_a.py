import module_b as m

class A(m.B):
    def foo(self):
        pass

def func(x):
    x.foo()
    x.bar()