class B:
    def bar(self):
        pass

class A(B):
    def foo(self):
        pass

def func(x):
    x.foo()
    x.bar()