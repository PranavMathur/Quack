import lark

#assigns a type to each node in the tree
class TypeChecker(lark.visitors.Visitor_Recursive):
    def __init__(self, types):
        self.variables = {} #set to store types of initialized variables
        self.types = types #method tables - used to find return values
    def __default__(self, tree):
        literals = { #map between node names and builtin type names
            'lit_number': 'Int',
            'lit_string': 'String',
            'lit_true': 'Bool',
            'lit_false': 'Bool',
            'lit_nothing': 'Nothing'
        }
        if tree.data in literals: #assign builtin type for literal token
            tree.type = literals[tree.data]
        elif tree.data == 'var': #search variables map for assigned type
            name = str(tree.children[0])
            tree.type = self.variables[name]
        elif tree.data == 'assign': #map the variable name to the given type
            left = tree.children[0]
            tree.type = str(tree.children[1])
            self.variables[str(left)] = tree.type
        elif tree.data == 'assign_imp':
            left = tree.children[0]
            tree.type = tree.children[1].type
            self.variables[str(left)] = tree.type
        elif tree.data in ('and_exp', 'or_exp'):
            left, right = tree.children
            #check that both operands are Bools
            if left.type != 'Bool' or right.type != 'Bool':
                raise ValueError('Operands of and/or must be Bool')
            #the type of a logical expression is always Bool
            tree.type = 'Bool'
        elif tree.data == 'condition':
            #check that conditional has type Bool
            if tree.children[0].type != 'Bool':
                raise ValueError('Type of condition must be Bool')
            #the type of a condition is always Bool
            tree.type = 'Bool'
        elif tree.data == 'm_call': #query the table for the return type
            left_type = tree.children[0].type #find type of receiver
            m_name = str(tree.children[1]) #get name of called function
            #retrieve parameter/return types of called function of receiver
            try:
                #attempt to retrieve information about method
                method = self.types[left_type]['methods'][m_name]
            except KeyError:
                #fail if method not found
                err = f'Could not resolve return type of {left_type}.{m_name}'
                raise ValueError(err) from None
            else:
                ret_type = method['ret'] #retrieve return type of method
                args = tree.children[2].children #fetch children of m_args
                #pluck types of given arguments
                arg_types = [child.type for child in args]
                #fetch types of expected arguments
                exp_types = method['params']
                #first check - check number of given arguments
                if len(arg_types) != len(exp_types):
                    #grammar!
                    plural = 's' if len(exp_types) > 1 else ''
                    e = (m_name, len(exp_types), plural, len(arg_types))
                    raise ValueError('%r expected %d arg%s, received %d' % e)
                #second check - check types of given arguments
                for rec, exp in zip(arg_types, exp_types):
                    if not is_compatible(rec, exp, self.types):
                        e = (m_name, exp, rec)
                        raise ValueError('%r expected %r, received %r' % e)
            tree.type = ret_type #set overall type of m_call node

#check if the first argument is a subclass of the second argument
def is_compatible(typ, sup, types):
    if typ == sup: #most common check - return true if args are equal
        return True
    #traverse up the tree while match is not found
    while types[typ]['super'] != typ:
        #set typ to typ's supertype
        typ = types[typ]['super']
        if typ == sup: #return true if match is found
            return True
    return False #no match was found
