from collections import defaultdict
import importlib
import inspect
import sys

from greentype.runner import ClassDefinition

class Indexer:
    _class_index = {}
    _function_index = {}
    _class_attributes_index = defaultdict(set)
    _module_index = {}

    def run(self, *args, **kwargs):
        raise NotImplementedError()

    def register_class(self, class_def):
        Indexer._class_index[class_def.qname] = class_def
        for attr in self.collect_class_attributes(class_def):
            Indexer._class_attributes_index[attr].add(class_def)

    def register_function(self, func_def):
        Indexer._function_index[func_def.qname] = func_def

    def register_module(self, module_def):
        Indexer._module_index[module_def.qname] = module_def

    def collect_class_attributes(self, class_def):
        return class_def.attributes


class SourcesIndexer(Indexer):
    def run(self, path):
        pass

class ReflexiveClassDefinition(ClassDefinition):
    def __init__(self, qname, bases, members):
        super().__init__(qname, None, bases, members)


class ReflectiveIndexer(Indexer):
    def run(self, module_name='builtins', package=None):
        def is_hidden(name):
            return name.startswith('_')

        module = importlib.import_module(module_name, package)
        for module_attr_name, module_attr in vars(module).items():
            if is_hidden(module_attr_name):
                continue
            if inspect.isclass(module_attr):
                class_name = module_attr.__qualname__
                class_bases = tuple(b.__qualname__ for b in module_attr.__bases__)
                attributes = [name for name in dir(module_attr) if not is_hidden(name)]
                self.register_class(ReflexiveClassDefinition(class_name, class_bases, attributes))


def main():
    sys.modules['greentype.stdlib'] = sys.modules[__name__]
    ReflectiveIndexer().run()
    for name, cls_def in Indexer._class_index.items():
        print('{}\n  {}'.format(name, '\n  '.join(cls_def.attributes)))

    import pprint
    pprint.pprint(Indexer._class_index.values())


if __name__ == '__main__':
    main()








