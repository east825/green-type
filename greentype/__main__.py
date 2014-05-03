from collections import defaultdict
import ast
import os
import sys


class FunctionVisitor(ast.NodeVisitor):
    def visit_FunctionDef(self, func_node):
        param_names = []
        param_names.extend(a.arg for a in func_node.args.args)
        param_names.extend(a.arg for a in func_node.args.kwonlyargs)

        param_aliases = {name: {name} for name in param_names}
        param_attributes = {name: set() for name in param_names}

        class Collector(ast.NodeVisitor):
            def visit_Assign(self, assignment_node):
                # for now without tuple packing/unpacking
                target, expr = assignment_node.targets[0], assignment_node.value
                # collect usages before assignment
                self.visit(expr)
                # skip packing/unpacking for now
                if isinstance(expr, (ast.List, ast.Tuple)) and isinstance(target, (ast.List, ast.Tuple)) \
                        and len(target.elts) == len(expr.elts):
                    for target, expr in zip(target.elts, expr.elts):
                        self._process_assignment(target, expr)
                elif isinstance(target, ast.Name):
                    self._process_assignment(target, expr)


            def _process_assignment(self, target, expr):
                if isinstance(target, ast.Name) and isinstance(expr, ast.Name):
                    for param, aliases in param_aliases.items():
                        updated = set(aliases)
                        if expr.id in aliases:
                            updated.add(target.id)
                        if target.id in aliases:
                            updated.remove(target.id)
                        param_aliases[param] = updated

            def visit_Attribute(self, attr_node):
                qualifier, attr_name = attr_node.value, attr_node.attr
                if isinstance(qualifier, ast.Name):
                    for param, aliases in param_aliases.items():
                        if qualifier.id in aliases:
                            param_attributes[param].add(attr_name)

            def visit_Subscript(self, subscript_node):
                qualifier, access = subscript_node.value, subscript_node.ctx
                if isinstance(qualifier, ast.Name):
                    for param, aliases in param_aliases.items():
                        if qualifier.id in aliases:
                            # What the heck is AugLoad / AugStore / Param
                            if isinstance(access, ast.Load):
                                param_attributes[param].add('__getitem__')
                            elif isinstance(access, ast.Store):
                                param_attributes[param].add('__setitem__')
                            elif isinstance(access, ast.Del):
                                param_attributes[param].add('__delitem__')


        for stmt in func_node.body:
            Collector().visit(stmt)

        param_types = []
        for name, in param_names:
            param_types.append('{}::{{{}}}'.format(name, ', '.join(param_attributes[name])))
        print('{}({})'.format(func_node.name, ', '.join(param_types)))


def main():
    file_path = os.path.abspath(sys.argv[1])
    with open(file_path) as f:
        root_node = ast.parse(f.read(), file_path)
        FunctionVisitor().visit(root_node)


if __name__ == '__main__':
    main()
