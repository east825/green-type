def qname_merge(n1, n2, accept_disjoint=True):
    # Do not use sep='.' for Python 2.x compatibility!
    parts1 = n1.split('.')
    parts2 = n2.split('.')
    if not n1 or not n2:
        return n2 or n1
    for n in range(len(parts2), 0, -1):
        if parts1[-n:] == parts2[:n]:
            return '.'.join(parts1 + parts2[n:])
    return '.'.join(parts1 + parts2) if accept_disjoint else None


def qname_head(name):
    _, _, head = name.rpartition('.')
    return head or None


def qname_tail(name):
    tail, _, _ = name.rpartition('.')
    return tail or None


def qname_split(name):
    tail, _, head = name.rpartition('.')
    return tail or None, head


def qname_drop(name, qualifier):
    if qname_qualified_by(name, qualifier) and qualifier:
        return name[len(qualifier + '.'):]
    return name


def qname_qualified_by(name, qualifier):
    if not qualifier:
        return True
    # parts1 = name.split('.')
    # parts2 = qualifier.split('.')
    # return parts1[:len(parts2)] == parts2
    return name == qualifier or name.startswith(qualifier + '.')


def partition_any(s, separators, from_end=False):
    for sep in separators:
        if from_end:
            right, _, left = s.rpartition(sep)
            if right:
                return right, left
        else:
            right, _, left = s.partition(sep)
            if left:
                return right, left
    return (None, s) if from_end else (s, None)


def camel_to_snake(s):
    """Translate CamelCase identifier to snake_case.

    If identifier is already in snake case it will be returned unchanged,
    except that leading and trailing underscores will be stripped.
    """
    words = []
    word = []
    prev_upper = False
    for c in s:
        if ((c.isupper() and not prev_upper) or not c.isalnum()) and word:
            words.append(''.join(word))
            word = []
        if c.isalnum():
            word.append(c.lower())
            prev_upper = c.isupper()
    if word:
        words.append(''.join(word))
    return '_'.join(words)
