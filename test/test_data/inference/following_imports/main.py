from sibling import SuperClass

class SubClass(SuperClass):
    def foo(self):
        pass

def func(x):
    x.foo()
