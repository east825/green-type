class Node:

    def __init__(self, name):
        super().__init__()
        self.name = name


class ClassDefinitionNode(Node):
    def __init__(self, name, bases, members):
        super().__init__(name)
        self.bases = tuple(bases)
        self.members = list(members)

    def __str__(self):
        return 'class {}({}) :: {{{}}}'.format(
            self.name,
            ', '.join(self.bases),
            ', '.join(self.members)
        )




