# Here we first try to find module called package.Foo.
# On Windows case insensitive file systems "package/foo.py" is indeed
# found and included in index with name "package.Foo" again.
from package import Foo
