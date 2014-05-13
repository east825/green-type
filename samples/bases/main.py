from sibling import B
class A(B):
    def foo(self):
        pass

    def bar(self):
        pass

def func(x):
    x.foo()
    x.bar()