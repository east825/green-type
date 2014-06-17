def func1(x):
    if True:
        return (x)
    elif False:
        return x + 2 # not counted as return value
    elif False:
        return x.foo # not counted as return value
    elif False:
        return x['key'] # not counted as return value
    return x

def func2(x):
    v1 = x + 42
    v2 = not x
    v3 = ~x
    v4 = x << 10
    v5 = x['key'] * 8 # not counted as operand
    v6 = x.foo % 2 # not counted as operand

def func3(x):
    v1 = dict(x)
    v2 = len(x.foo) # not counted as argument
    v3 = filter(None, x | x['key']) # not counted as argument
    v4 = int(x, base=16)