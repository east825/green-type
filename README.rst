Green-type
==========

My work on this little project started from the following question. If you have
something__ that already uses almost everything trying to infer types for
Python programs, including knowledge about

#. literals of built-in types
#. class constructor invocations
#. Python 3 function annotations__
#. types from docstrings in Sphinx__ and EpyDoc__ formats
#. default values of function parameters
#. explicit type checks in ``isinstance()`` form
#. types of arguments passed to function in its call sites
#. thorough flow-sensitive analysis of language constructs
#. runtime type information collected during `dubugging sessions`__

What else you can do?

Well, not much really. After reading quite a few of papers about inference
in Self, Smalltalk, Ruby and Python I came to a couple of things left.

First of all, structural types awareness, where information about attributes
accessed on parameters (messages passed) in functions body is used to restrict
possible types of its arguments.

Additionally it seems in fact that such information can not only prevent some
``AttributeError`` statically, but also can be used to *suggest possible
classes* (nominal types) in places where other approaches can't. If you
curious, similar approach to object types lies in the heart of OCaml type system.

Secondly, so called CPA [Ageseen95]_ algorithm that has been used in some
existing projects and has established itself as effective way to infer types for
function with parametric polymorphism. In CPA type of the function is analyzed
for *every used combination* (calculated with Cartesian product,
hence the name) of its arguments types.

In its current state green-type is very straight-forward/brute-force/rude
prototypical implementation of my first idea.

Run it on your project and it will show you some statistic
about which function parameter types can be successfully inferred with
information about accessed attributes, which cannot and where there is an
ambiguity.

For example, running it on itself shows::

    $ python3 runner.py --dump-parameters --target greentype.core.resolve_name .
    Analysing built-in modules...
    Analyzing user modules starting from '/home/east825/develop/repos/green-type'
    Started inferring parameter types
    Stopped inferring: 0.02s spent

    Total indexed: 325 classes with 509 attributes, 174 functions with 318 parameters
    Most frequently accessed parameters (top 20):
    10 attributes : ast.literal_eval._convert.node::{n, op, left, right, elts, operand, values, value, s, keys}
        6 attributes : greentype.ast2.nodes.Parameter.from_ast.args::{vararg, kwonlyargs, kwarg, kw_defaults, defaults, args}

        ... statistics, statistics...

    Parameters statistic:
    233 (73.27%) parameters have no attributes (types cannot be inferred):
    However, of them:
        - 69.53% used directly somehow (no attribute access or subscripts)
        - 40.34% passed as arguments to other function
        - 4.29% used as operands in arithmetic or logical expressions
        - 0.86% returned from function
    23 (7.23%) parameters have some parameters, but no type inferred,
    32 (10.06%) parameters have exactly one type inferred,
    30 (9.43%) parameters have more then one inferred type (scattered types)

        ... more statistics, statistics...

    Parameters
    Parameter greentype.core.resolve_name.module::{imports, path, definitions, qname} ~ {class greentype.core.ModuleDefinition(Definition)}:
    - used directly: 5 times
    - passed to other function: 2 times
    - used in arithmetic and logical expressions 0 times
    - returned: 0 times

__ http://www.jetbrains.com/pycharm/
__ http://legacy.python.org/dev/peps/pep-3107/
__ http://sphinx-doc.org/domains.html#the-python-domain
__ http://epydoc.sourceforge.net/manual-epytext.html
__ http://blog.jetbrains.com/pycharm/2013/02/dynamic-runtime-type-inference-in-pycharm-2-7/

.. [Ageseen95] Ole Agesseen - The Cartesian Product Algorithm Simple and
    Precise Type Inference of Parametric Polymorphism. 1995