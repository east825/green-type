import enum

class TypeRelation(enum.Enum):
    COVARIANT = 0
    INVARIANT = 1
    CONTRAVARIANT = 2


class Type:
    def name(self):
        return type(self).__name__

    def is_builtin(self):
        return False

    def definition_node(self):
        return None

    def attributes(self):
        return []

    def relation(self, other_type):
        return TypeRelation.INVARIANT


class CollectionType(Type):
    def element_type(self):
        pass


class PrimitiveType(Type):
    """Built-in immutable not compound types: int, float and bool"""
    def is_builtin(self):
        return True

    def relation(self, other_type):
        if type(self) is type(other_type):
            return TypeRelation.COVARIANT
        return TypeRelation.INVARIANT


class IntegerType(PrimitiveType):
    pass


class FloatType(PrimitiveType):
    pass


class BooleanType(PrimitiveType):
    pass


class NoneType(PrimitiveType):
    pass


class CallableType(Type):
    def argument_types(self):
        pass

    def return_type(self):
        pass

    def return_type_for_call_site(self, call_site):
        pass


class ClassType(CallableType):
    def __init__(self, qualified_name, node):
        super().__init__()
        self.node = node
        self.qualified_name = qualified_name

    def as_structural(self):
        return StructuralType.from_class_type(self)


class StructuralType(Type):
    def __init__(self, attributes):
        super().__init__()
        self._attributes = list(attributes)

    def attributes(self):
        return tuple(self._attributes)


    @classmethod
    def from_class_type(cls, class_type, with_superclasses=False):
        pass

    def possible_classes(self):
        return []


    def __str__(self, *args, **kwargs):
        return 'StructuralType({})'.format(', '.join(self._attributes))


class UnionType(Type):

    def __init__(self, *types):
        super().__init__()
        self._types = tuple(types)


    @classmethod
    def empty(cls):
        return UnionType()









