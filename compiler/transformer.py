import lark
from lark import Tree

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

#creates Main class from code at the end of the file
@lark.v_args(tree=True)
class ClassTransformer(lark.Transformer):
    def __init__(self, name):
        self.name = name
    #process code at the end of the file
    def main_block(self, tree):
        #do nothing if there is no code to be executed
        if not tree.children:
            return tree
        #create and return a subtree for a new main class
        #the new class will have only one method, the constructor
        return Tree('class_', [
            #class signature contains class name, arguments, and superclass
            Tree('class_sig', [
                self.name,
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
                        Tree('statement_block', tree.children)
                    ])
                ])
            ])
        ])
    #move the main class created above into the correct subtree
    def program(self, tree):
        classes = tree.children[0]
        #remove main class subtree from tree
        main_class = tree.children.pop(1)
        #do nothing if no main class was created
        if not main_class.children:
            return tree
        #add main class to children of classes block
        classes.children.append(main_class)
        return tree
