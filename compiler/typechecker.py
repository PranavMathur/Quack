import lark
from compiler.errors import CompileError

#assigns a type to each node in the tree
class TypeChecker(lark.visitors.Visitor_Recursive):
    def __init__(self, types):
        self.variables = {} #set to store types of initialized variables
        self.types = types #method tables - used to find return values
    #visit children of tree and root
    #return true if any of the childrens' types were changed
    #or if the root's type was changed
    def visit(self, tree):
        changed = False #changed is initially false
        for child in tree.children:
            if isinstance(child, lark.Tree):
                #if child's type was changed, return true
                ret = self.visit(child)
                changed = changed or ret
        #if root's type was changed, return true
        ret = self._call_userfunc(tree)
        return changed or ret
    def __default__(self, tree):
        orig = tree.type #keep track of original type of tree
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
            #get the name of the variable we are assigning
            name = str(tree.children[0])
            #get the given type of the right side of the assignment
            given_type = str(tree.children[1])
            #get the implied type of the right side of the assignment
            imp_type = tree.children[2].type
            if not is_compatible(imp_type, given_type, self.types):
                e = '%r is not a subclass of %r' % (imp_type, given_type)
                raise CompileError(e)
            #get the current type of the variable if it exists, blank otherwise
            old_type = self.variables.get(name, '')
            #get the common ancestor of the given type and the old type
            new_type = common_ancestor(old_type, given_type, self.types)
            #set the type of the assignment and the variable to the new type
            tree.type = new_type
            self.variables[name] = new_type
        elif tree.data == 'assign_imp':
            #get the name of the variable we are assigning
            name = str(tree.children[0])
            #get the implied type of the right side of the assignment
            imp_type = tree.children[1].type
            #get the current type of the variable if it exists, blank otherwise
            old_type = self.variables.get(name, '')
            #get the common ancestor of the implied type and the old type
            new_type = common_ancestor(old_type, imp_type, self.types)
            #set the type of the assignment and the variable to the new type
            tree.type = new_type
            self.variables[name] = new_type
        elif tree.data in ('and_exp', 'or_exp'):
            left, right = tree.children
            #check that both operands are Bools
            if left.type != 'Bool' or right.type != 'Bool':
                raise CompileError('Operands of and/or must be Bool')
            #the type of a logical expression is always Bool
            tree.type = 'Bool'
        elif tree.data == 'condition':
            #check that conditional has type Bool
            if tree.children[0].type != 'Bool':
                raise CompileError('Type of condition must be Bool')
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
                err = f'Could not find method {m_name} of {left_type}'
                raise CompileError(err)
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
                    raise CompileError('%r expected %d arg%s, received %d' % e)
                #second check - check types of given arguments
                for rec, exp in zip(arg_types, exp_types):
                    if not is_compatible(rec, exp, self.types):
                        e = (m_name, exp, rec)
                        raise CompileError('%r expected %r, received %r' % e)
            tree.type = ret_type #set overall type of m_call node
        #return whether tree's type has changed
        return tree.type != orig

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

#find the depth of a node in the given inheritance hierarchy
#Obj has depth 0, direct subclasses of Obj have depth 1, etc.
def depth(typ, types):
    ret = 0 #counter
    #while typ is not Obj, increment the counter and elevate typ by one level
    while types[typ]['super'] != typ:
        ret += 1
        typ = types[typ]['super']
    return ret

#find the first class that is a superclass of the two arguments
def common_ancestor(typ1, typ2, types):
    #if either of the arguments are empty, return the other argument
    if not typ1:
        return typ2
    if not typ2:
        return typ1
    if typ1 == typ2: #most common check - return typ1 if args are equal
        return typ1
    #find difference in depth of the nodes
    delta = depth(typ1, types) - depth(typ2, types)
    #if typ1 is deeper than typ2, elevate typ1 by the difference
    #this is a no-op if depth is negative
    for i in range(delta):
        typ1 = types[typ1]['super']
    #if typ2 is deeper than typ1, elevate typ2 by the difference
    #this is a no-op if depth is positive
    for i in range(-delta):
        typ2 = types[typ2]['super']
    #elevate both types concurrently until they point to the same class
    while typ1 != typ2:
        typ1 = types[typ1]['super']
        typ2 = types[typ2]['super']
    return typ1 #both point to the same value, so return one of them
