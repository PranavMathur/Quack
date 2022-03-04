import lark
from lark import Tree
from copy import deepcopy
from compiler.errors import CompileError


#loads user-defined classes into the method table
def load_classes(tree, types):
    classes = tree.children[0]
    for class_ in classes.children:
        #unpack children for convenience
        class_sig, class_body = class_.children
        #extract class name
        c_name = str(class_sig.children[0])

        formal_args = class_sig.children[1]
        #get formal argument types for the constructor
        arg_types = [str(arg.children[1]) for arg in formal_args.children]

        #extract superclass's name - Obj if none is given
        super_type = str(class_sig.children[2] or 'Obj')
        #retrieve information about superclass from method table
        super_class = types[super_type]
        #make a copy of the superclass's methods for this table
        super_methods = deepcopy(super_class['methods'])
        #make a copy of the superclass's fields for this table
        super_fields = deepcopy(super_class['fields'])

        #initialize this class's entry in the method table
        types[c_name] = {
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

        #add constructor method to class's methods
        methods.children.insert(0, con_method)

        #iterate over user-defined methods
        for method in methods.children:
            #extract method name from AST
            m_name = str(method.children[0])
            formal_args = method.children[1]
            #get formal argument types for the method
            arg_types = [str(arg.children[1]) for arg in formal_args.children]
            #extract return type of function
            #if return type is not given, infer that function returns 'none'
            ret_type = str(method.children[2] or 'Nothing')

            #add (or update) user-defined method to method table
            types[c_name]['methods'][m_name] = {
                'params': arg_types,
                'ret': ret_type
            }

        #remove constructor child of class, as the constructor was added
        #to the methods block
        class_body.children.pop(0)
