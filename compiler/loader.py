import lark
from copy import deepcopy
from compiler.errors import CompileError

class ClassLoader(lark.visitors.Visitor_Recursive):
    def __init__(self, types):
        self.types = types
    def class_(self, tree):
        class_sig, class_body = tree.children
        c_name = str(class_sig.children[0])
        formal_args = class_sig.children[1]
        arg_types = [str(arg.children[1]) for arg in formal_args.children]
        super_type = str(class_sig.children[2] or 'Obj')
        super_class = self.types[super_type]
        super_methods = deepcopy(super_class['methods'])
        super_fields = deepcopy(super_class['fields'])
        self.types[c_name] = {
            'super': super_type,
            'methods': super_methods,
            'fields': super_fields
        }
        self.types[c_name]['methods']['$constructor'] = {
            'params': arg_types,
            'ret': 'Nothing'
        }
        constructor, methods = class_body.children
        for method in methods.children:
            self.types[c_name]['methods'][method.m_name] = {
                'params': method.arg_types,
                'ret': method.ret_type
            }
    def method(self, tree):
        tree.m_name = str(tree.children[0])
        formal_args = tree.children[1]
        tree.arg_types = [str(arg.children[1]) for arg in formal_args.children]
        tree.ret_type = str(tree.children[2] or '-')
