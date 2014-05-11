from os import *

def func(x, *, y):
    x.pop()
    z = x
    n = z.bar
    if True:
        y.baz.quux()
        print(y.bar)
    def nested_func():
        pass

class A(object):
    CONST = 42
    class B:
        def method(self, x):
            self.foo()
            self.bar()
            self.baz()
            self.quux()
            x.upper()
