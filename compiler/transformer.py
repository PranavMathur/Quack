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

#helper method to create a new tree with a "type" attribute
def typed_tree(*args):
    ret = Tree(*args)
    ret.type = ''
    return ret

#operates on the tree as it is created
#desugars binary operators into method calls
@lark.v_args(tree=True)
class OpTransformer(lark.Transformer):
    #transform the tree, then set its "type" attribute
    def _transform_tree(self, tree):
        ret = super()._transform_tree(tree)
        ret.type = ''
        return ret
    #"!=" is translated into "==" followed by a negation
    def notequals(self, tree):
        #children of the intermediate call's node
        eq_children = [
            tree.children[0], #receiver of "!=" (LHS)
            'EQUALS',
            typed_tree('args', tree.children[1:]) #argument (RHS)
        ]
        #intermediate call's node
        eq_call = typed_tree('m_call', eq_children)
        #children of the returned node
        new_children = [
            eq_call, #receiver of negation
            'NEGATE',
            typed_tree('args', []) #boolean negation has no arguments
        ]
        return typed_tree('m_call', new_children)
    #create a method call subtree with the appropriate binary op function
    def op_transform(self, data, children, meta):
        #desugar binary operations into method calls
        new_children = [
            children[0], #receiver object
            data.upper(), #name of operator
            typed_tree('args', children[1:]) #argument object, if provided
        ]
        return typed_tree('m_call', new_children)
    #create an assignment subtree that assigns to the result of a method call
    def assign_op(self, data, children, meta):
        method = data[:-7].upper() #extract the appropriate binary operator
        left, right = children #unpack the arguments to the operator
        var_node = typed_tree('var', [left]) #create the variable node for the LHS
        method_children = [
            var_node, #receiver object
            method, #name of binary op's associated method
            typed_tree('args', [right]) #argument subtree
        ]
        #create the method call subtree
        method_node = typed_tree('m_call', method_children)
        assign_children = [
            left, #LHS of assignment
            None, #let the type checker imply the type
            method_node #RHS of assignment
        ]
        #create the assignment subtree
        return typed_tree('assign', assign_children)
    def __default__(self, data, children, meta):
        if data in ops: #only desugar certain nodes
            return self.op_transform(data, children, meta)
        elif data in assign_ops:
            return self.assign_op(data, children, meta)
        else:
            return typed_tree(data, children, meta)

@lark.v_args(tree=True)
class ClassTransformer(lark.Transformer):
    pass

class TypeTransformer(lark.Transformer):
    def _transform_tree(self, tree):
        ret = super()._transform_tree(tree)
        ret.type = ''
        return ret
