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
        try:
            #retrieve information about superclass from method table
            super_class = types[super_type]
        except KeyError:
            e = 'Could not find %r' % super_type
            raise CompileError(e, class_.meta)
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


def create_main(tree, name):
    #remove main class subtree from program tree
    main_block = tree.children.pop(1)
    #do nothing if no main class exists
    if not main_block.children:
        return

    #create a subtree for a new main class
    #the new class will have only one method, the constructor
    main_class = Tree('class_', [
        #class signature contains class name, arguments, and superclass
        Tree('class_sig', [
            name,
            Tree('formal_args', []),
            'Obj'
        ]),
        #class body contains methods
        #the grammar says there should be a constructor subtree,
        #but that is removed in the class loader
        Tree('class_body', [
            Tree('methods', [
                #one method - the constructor contains executable code
                #this constructor takes no arguments
                #the children of the statement_block are the children
                #of the original main_block
                Tree('method', [
                    '$constructor',
                    Tree('formal_args', []),
                    'Nothing',
                    Tree('statement_block', main_block.children)
                ])
            ])
        ])
    ])

    #add main class to children of classes block
    classes = tree.children[0]
    classes.children.append(main_class)
