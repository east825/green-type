class SuperClass(object):
    bar = 42

class SubClass(SuperClass):
    def foo(self):
        pass

def function(normal,
             unused,
             used_as_argument,
             used_as_operand,
             returned):
    normal.foo()
    normal.bar()
    oct(used_as_argument)
    if used_as_operand & 0x0F:
        return returned

