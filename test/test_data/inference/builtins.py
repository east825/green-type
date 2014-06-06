def check_collections(x, y):
    # dict or set
    x.pop() and x.update()

    # list only
    y.insert(0, 42) and y.sort()

def check_strings(x, y):
    # PY2: unicode/str
    # PY3: str/bytes
    if x.upper():
        return x.split(';')

    # PY2: unicode / str
    # PY3: str
    y.upper()
    # without call to upper() some *Encoder classes from _multibytecodec
    # on Windows are matched as well
    y.encode()

