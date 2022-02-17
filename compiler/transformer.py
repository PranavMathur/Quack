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
        #children of the intermediate call's node
        eq_children = [
            tree.children[0], #receiver of "!=" (LHS)
            'EQUALS',
            Tree('args', tree.children[1:]) #argument (RHS)
        ]
        #intermediate call's node
        eq_call = Tree('m_call', eq_children)
        #children of the returned node
        new_children = [
            eq_call, #receiver of negation
            'NEGATE',
            Tree('args', []) #boolean negation has no arguments
        ]
        return Tree('m_call', new_children)
    #create a method call subtree with the appropriate binary op function
    def op_transform(self, data, children, meta):
        #desugar binary operations into method calls
        new_children = [
            children[0], #receiver object
            data.upper(), #name of operator
            Tree('args', children[1:]) #argument object, if provided
        ]
        return Tree('m_call', new_children)
    #create an assignment subtree that assigns to the result of a method call
    def assign_op(self, data, children, meta):
        method = data[:-7].upper() #extract the appropriate binary operator
        left, right = children #unpack the arguments to the operator
        var_node = Tree('var', [left]) #create the variable node for the LHS
        method_children = [
            var_node, #receiver object
            method, #name of binary op's associated method
            Tree('args', [right]) #argument subtree
        ]
        #create the method call subtree
        method_node = Tree('m_call', method_children)
        assign_children = [
            left, #LHS of assignment
            None, #let the type checker imply the type
            method_node #RHS of assignment
        ]
        #create the assignment subtree
        return Tree('assign', assign_children)
    def __default__(self, data, children, meta):
        if data in ops: #only desugar certain nodes
            return self.op_transform(data, children, meta)
        elif data in assign_ops:
            return self.assign_op(data, children, meta)
        else:
            return Tree(data, children, meta)

@lark.v_args(tree=True)
class ClassTransformer(lark.Transformer):
    pass

class TypeTransformer(lark.Transformer):
    #set the tree's "type" attribute
    def _transform_tree(self, tree):
        ret = super()._transform_tree(tree)
        ret.type = ''
        return ret
