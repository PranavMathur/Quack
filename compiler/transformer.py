import lark

ops = (
    'plus',
    'minus',
    'times',
    'divide',
    'neg',
    'negate',
    'equals',
    'less',
    'atmost',
    'more',
    'atleast'
)

#operates on the tree as it is created
#desugars binary operators into method calls
@lark.v_args(tree=True)
class Transformer(lark.Transformer):
    #"!=" is translated into "==" followed by a negation
    def notequals(self, tree):
        #children of the intermediate call's node
        eq_children = [
            tree.children[0], #receiver of "!=" (LHS)
            'EQUALS',
            lark.Tree('m_args', tree.children[1:]) #argument (RHS)
        ]
        #intermediate call's node
        eq_call = lark.Tree('m_call', eq_children)
        #children of the returned node
        new_children = [
            eq_call, #receiver of negation
            'NEGATE',
            lark.Tree('m_args', []) #boolean negation has no arguments
        ]
        return lark.Tree('m_call', new_children)
    #create a method call subtree with the appropriate binary op function
    def __default__(self, data, children, meta):
        #desugar binary operations into method calls
        if data in ops: #only desugar certain nodes
            new_children = [
                children[0], #receiver object
                data.upper(), #name of operator
                lark.Tree('m_args', children[1:]) #argument object, if provided
            ]
            return lark.Tree('m_call', new_children)
        else:
            return lark.Tree(data, children, meta)
