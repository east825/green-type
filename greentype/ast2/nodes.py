import abc
import ast
import enum
from symbol import parameters
import weakref
import itertools


class BaseNode:
    def __init__(self):
        super().__init__()
        self.ast_node = None
        self._parent = weakref.ref()
        self._children = []

    @property
    def parent_node(self):
        return self._parent()

    @parent_node.setter
    def parent_node(self, node):
        self._parent = weakref.ref(node)

    @abc.abstractmethod
    def children(self):
        pass


    def __str__(self):
        pairs = []
        for name, attr in vars(self).items():
            if name.startswith('_') or isinstance(attr, (ast.AST, BaseNode)):
                continue
            pairs.append('{}={!r}'.format(name, attr))
        return '{}({})'.format(type(self).__name__, ', '.format(pairs))


    @classmethod
    @abc.abstractmethod
    def from_ast(cls, ast_node, ast_parent=None):
        pass


class StubNode(BaseNode):
    def __init__(self, node):
        super().__init__()
        self.ast_node = node

    @property
    def name(self):
        return getattr(self.ast_node, 'name') or getattr(self.ast_node, 'id')

    def children(self):
        if self.ast_node:
            return ast.iter_child_nodes(self.ast_node)
        return []

    @classmethod
    def from_ast(cls, ast_node, ast_parent=None):
        return StubNode(ast_node)


class StatementsList(BaseNode):
    def __init__(self, statements):
        super().__init__()
        self.statements = statements

    @classmethod
    def from_ast(cls, body, ast_parent=None):
        assert isinstance(body, list)
        return StatementsList(body)


class ParameterType(enum.IntEnum):
    NORMAL = 0
    VARARG = 1
    KEYWORD_VARARG = 2
    KEYWORD_ONLY = 3


class Parameter(BaseNode):
    def __init__(self, name, default_value, param_type):
        super().__init__()
        self.name = name
        self.default_value = default_value
        self.param_type = param_type

    @property
    def children(self):
        if self.default_value:
            return [self.default_value]
        return []


    @classmethod
    def from_ast(cls, ast_node, args=None):
        assert isinstance(args, ast.arguments)
        if isinstance(ast_node, str):
            if args.vararg == ast_node:
                return Parameter(ast_node, None, ParameterType.VARARG)
            if args.kwarg == ast_node:
                return Parameter(ast_node, None, ParameterType.KEYWORD_VARARG)
            raise ValueError('String parameter node should be either *node or **node')
        assert isinstance(ast_node, ast.Param)
        if ast_node in args.args:
            params, defaults, kind = args.args, args.defaults, ParameterType.NORMAL
        elif ast_node in args.kwonlyargs:
            params, defaults, kind = args.kwonlyargs, args.kw_defaults, ParameterType.KEYWORD_ONLY
        else:
            raise ValueError('Parameter node does not belong to arguments list')
        paired = itertools.zip_longest(reversed(params), reversed(defaults))
        for param, default in paired:
            if param is ast_node:
                return Parameter(param.arg, default, kind)


class FunctionDefinition(BaseNode):
    def __init__(self, name, body):
        super().__init__()
        self.name = name
        self.parameters = parameters
        self.body = body

    def children(self):
        return [self.parameters, self.body]


class ClassDefinition(BaseNode):
    def __init__(self, name, body, bases=(), metaclass=None):
        super().__init__()
        self.name = name
        self.bases = bases
        self.body = body
        self.metaclass = metaclass

    def children(self):
        nodes = []
        if self.bases:
            nodes.append(self.bases)
        return [self.bases]

    @classmethod
    def from_ast(cls, ast_node, ast_parent=None):
        super().from_ast(ast_node, ast_parent)


