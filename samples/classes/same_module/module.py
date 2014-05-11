class A:
    def foo(self):
        pass

class B(A):
    def bar(self):
        pass

def func(x):
    x.foo()
    x.bar()