import datetime

class MyDate(datetime.datetime):
    def foo(self):
        pass

def func(x):
    x.foo
    x.hour