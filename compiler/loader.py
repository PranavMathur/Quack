import lark
from lark import Tree
from copy import deepcopy
from compiler.errors import CompileError

#loads user-defined classes into the method table
class ClassLoader(lark.visitors.Visitor_Recursive):
    def __init__(self, types):
        self.types = types #method table
    def class_(self, tree):
        #unpack children for convenience
        class_sig, class_body = tree.children
        #extract class name
        c_name = str(class_sig.children[0])
        formal_args = class_sig.children[1]
        #get formal argument types for the constructor
        arg_types = [str(arg.children[1]) for arg in formal_args.children]
        #extract superclass's name - Obj if none is given
        super_type = str(class_sig.children[2] or 'Obj')
        #retrieve information about superclass from method table
        super_class = self.types[super_type]
        #make a copy of the superclass's methods for this table
        super_methods = deepcopy(super_class['methods'])
        #make a copy of the superclass's fields for this table
        super_fields = deepcopy(super_class['fields'])
        #initialize this class's entry in the method table
        self.types[c_name] = {
            'super': super_type,
            'methods': super_methods,
            'fields': super_fields
        }
        #unpack children for convenience
        constructor, methods = class_body.children
        #create subtree for the constructor method
        con_method = Tree('method', [
            '$constructor',
            formal_args,
            'Nothing',
            Tree('statement_block', constructor.children)
        ])
        #manually set argument/return types for the constructor
        con_method.m_name = '$constructor'
        con_method.arg_types = arg_types
        con_method.ret_type = 'Nothing'
        #add constructor method to class's methods
        if con_method.children[3].children:
            methods.children.insert(0, con_method)
        #iterate over user-defined methods
        for method in methods.children:
            #add (or update) user-defined method to method table
            self.types[c_name]['methods'][method.m_name] = {
                'params': method.arg_types,
                'ret': method.ret_type
            }
        #remove constructor child of class, as the constructor was added
        #to the methods block
        class_body.children.pop(0)
    #infer the type of a user-defined method
    def method(self, tree):
        #extract method name from AST
        tree.m_name = str(tree.children[0])
        formal_args = tree.children[1]
        #get formal argument types for the method
        tree.arg_types = [str(arg.children[1]) for arg in formal_args.children]
        #extract return type of function
        #if return type is not given, infer that function returns 'none'
        tree.ret_type = str(tree.children[2] or 'Nothing')
