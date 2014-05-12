from unittest import TestCase

class MyTestCase(TestCase):
    def foo(self):
        pass

def func(x):
    x.setUp()
    x.foo()
    x.tearDown()