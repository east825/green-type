# such cases are not resolved because will lead to
# infinite recursion due to memoization implementation

class A(object):
    pass

class A(A):
    pass