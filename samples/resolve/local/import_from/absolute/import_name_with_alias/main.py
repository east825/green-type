from module import B as Base

class A(Base):
    def foo(self):
        pass

def func(x):
    x.foo()
    x.bar()