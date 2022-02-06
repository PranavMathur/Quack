import lark

ops = (
    'plus',
    'minus',
    'times',
    'divide',
    'neg',
    'negate',
    'equals',
    'notequals',
    'less',
    'atmost',
    'more',
    'atleast'
)

#operates on the tree as it is created
#desugars binary operators into method calls
@lark.v_args(tree=True)
class Transformer(lark.Transformer):
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
