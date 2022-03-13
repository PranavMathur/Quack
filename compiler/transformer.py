import lark
from lark import Tree
from compiler.errors import CompileError

ops = (
    'plus',
    'minus',
    'times',
    'divide',
    'mod',
    'neg',
    'negate',
    'equals',
    'less',
    'atmost',
    'more',
    'atleast'
)

assign_ops = (
    'plus_equals',
    'minus_equals',
    'times_equals',
    'divide_equals',
    'mod_equals'
)


#operates on the tree as it is created
#desugars binary operators into method calls
@lark.v_args(tree=True)
class OpTransformer(lark.Transformer):
    #"!=" is translated into "==" followed by a negation
    def notequals(self, tree):
        #create and return method call subtree
        return Tree('m_call', [
            Tree('m_call', [ #receiver object of NEGATE is a method call
                tree.children[0], #receiver of EQUALS call
                'EQUALS',
                Tree('args', tree.children[1:]) #argument to EQUALS call
            ]),
            'NEGATE',
            Tree('args', []) #NEGATE takes no arguments
        ])

    def store_field(self, tree):
        #rearrange a store_field node to look more like an assignment
        #the grammar causes store_field to have a load_field child,
        #and improperly accepts a method or constructor call as the LHS,
        #both of which are fixed here
        load, value = tree.children #unpack children for convenience
        #fail if LHS is not a field access
        if load.data != 'load_field':
            #customize error message
            typ = 'method' if load.data == 'm_call' else 'constructor'
            e = 'Cannot assign to a %s call' % typ
            raise CompileError(e, tree.meta)

        #unpack children of load_field for convenience
        obj, field = load.children
        #construct return store_field node
        #store_field now has the object, the name of the field, and the value
        return Tree('store_field', [
            obj,
            field,
            value
        ])

    def ret_exp(self, tree):
        #transform an empty return into a return none
        ret_val = tree.children[0]
        if ret_val is None:
            ret_val = Tree('lit_nothing', [])
            return Tree('ret_exp', [ret_val])
        return tree

    def LONG_STRING(self, token):
        #sanitize triple quoted string
        return '"' + token[3:-3].replace('\n', '\\n') + '"'

    #create a method call subtree with the appropriate binary op function
    def op_transform(self, data, children, meta):
        #desugar binary operations into method calls
        return Tree('m_call', [
            children[0], #receiver object
            data.upper(), #name of operator
            Tree('args', children[1:]) #argument object, if provided
        ])

    #create an assignment subtree that assigns to the result of a method call
    def assign_op(self, data, children, meta):
        method = data[:-7].upper() #extract the appropriate binary operator
        left, right = children #unpack the arguments to the operator
        #check if the LHS is a field access or just an lvalue
        if isinstance(children[0], Tree) and children[0].data == 'load_field':
            #handle assignment operators on fields
            #unpack object and field name for convenience
            obj, field = children[0].children

            #create the assignment subtree
            return Tree('store_field', [
                Tree('load_field', [
                    obj, #object on which to set a field
                    field #name of the field to set
                ]),
                Tree('m_call', [ #value to set the field to
                    Tree('load_field', [ #LHS of operation is the current value
                        obj, #object from which to load a value
                        field #name of the field to load
                    ]),
                    method, #name of binary op's associated method
                    Tree('args', [right]) #argument subtree
                ])
            ])

        else:
            if isinstance(left, Tree):
                left = left.children[0]
            #create the assignment subtree

            return Tree('assign', [
                left, #LHS of assignment
                None, #let the type checker imply the type
                Tree('m_call', [ #RHS of assignment
                    Tree('var', [left]), #receiver object
                    method, #name of binary op's associated method
                    Tree('args', [right]) #argument subtree
                ])
            ])

    def __default__(self, data, children, meta):
        if data in ops: #only desugar certain nodes
            return self.op_transform(data, children, meta)
        elif data in assign_ops:
            return self.assign_op(data, children, meta)
        else:
            return Tree(data, children, meta)
