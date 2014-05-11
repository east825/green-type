x = 'foo'
y = 42
z = [None]

x, y = y, x

(x, y), z = (y, x), z

x, *y = z

x, (x, *y) = x, z