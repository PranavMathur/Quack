import lark
from compiler.errors import CompileError


#assigns a type to each node in the tree
class TypeChecker(lark.visitors.Visitor_Recursive):
    def __init__(self, types):
        self.variables = {} #set to store types of initialized variables
        self.types = types #method tables - used to find return values
        self.current_class = '' #name of the current class being checked
        self.current_method = '' #name of the current method being checked

    #visit children of tree and root
    #return true if any of the childrens' types were changed
    #or if the root's type was changed
    def visit(self, tree):
        if tree.data == 'class_':
            #extract the current class name
            self.current_class = str(tree.children[0].children[0])

        elif tree.data == 'method':
            #extract the current method name
            self.current_method = str(tree.children[0])
            #if this tree has been checked before, it will have a variables map
            #reuse the old map if this is the case
            if hasattr(tree, 'variables'):
                self.variables = tree.variables
            else:
                #if this tree has not been checked, initialize a variables map
                #"this" is an object of the current type
                self.variables = {'this': self.current_class}
                #store the variables map for future use
                tree.variables = self.variables
            #extract formal_args node from subtree
            formal_args = tree.children[1].children
            #iterate over formal parameters
            for arg in formal_args:
                #extract name and type from formal parameter
                name, type = arg.children
                #add name of parameter to variables set
                self.variables[str(name)] = str(type)

        elif tree.data == 'type_alternative':
            return self._typecase(tree)

        changed = False #changed is initially false
        for child in tree.children:
            if isinstance(child, lark.Tree):
                #if child's type was changed, return true
                ret = self.visit(child)
                changed = changed or ret
        #if root's type was changed, return true
        if not hasattr(tree, 'type'):
            tree.type = ''
        orig_type = tree.type #keep track of original type of tree
        self._call_userfunc(tree)
        return changed or tree.type != orig_type

    def _typecase(self, tree):
        #unpack children for convenience
        name, type, block = tree.children
        #store original type of the typecase variable
        #and remove it from the variables map
        orig_type = self.variables.pop(name, None)
        #set the type of the typecase variable unconditionally
        #for the entirety of the block
        self.variables[name] = type
        #type check the block and store whether it had any changes
        changed = self.visit(block)
        #if the name was already in the variable set, restore its value
        if orig_type:
            self.variables[name] = orig_type
        else:
            #if the name did not exist before, purge it from the variable set
            del self.variables[name]
        return changed

    def __default__(self, tree):
        #initializes the tree's type if this is the first pass of the checker
        if not hasattr(tree, 'type'):
            tree.type = ''
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

    def var(self, tree): #search variables map for assigned type
        name = str(tree.children[0])
        tree.type = self.variables[name]

    def load_field(self, tree):
        #unpack children for convenience
        obj, field = tree.children
        #convert field from token to string
        field = str(field)
        try:
            #attempt to retrieve type of field from method table
            field_type = self.types[obj.type]['fields'][field]
        except KeyError:
            #fail if field was not found
            e = 'Could not find field %r of %r' % (field, obj.type)
            raise CompileError(e, tree.meta)
        #update type of subtree
        tree.type = field_type

    def assign(self, tree): #map the variable name to the given type
        #get the name of the variable we are assigning
        name = str(tree.children[0])
        #get the given type of the right side of the assignment
        given_type = str(tree.children[1])
        if tree.children[1] is not None:
            given_type = str(tree.children[1])
        else:
            given_type = tree.children[2].type
        #get the implied type of the right side of the assignment
        imp_type = tree.children[2].type

        if not is_subclass(imp_type, given_type, self.types):
            e = '%r is not a subclass of %r' % (imp_type, given_type)
            raise CompileError(e, tree.meta)

        #get the current type of the variable if it exists, blank otherwise
        old_type = self.variables.get(name, '')
        #get the common ancestor of the given type and the old type
        new_type = common_ancestor(old_type, given_type, self.types)
        #set the type of the assignment and the variable to the new type
        tree.type = new_type
        self.variables[name] = new_type

        #ensure that the explicit type given is compatible with the new type
        if tree.children[1] is not None:
            given_type = str(tree.children[1])
            if not is_subclass(new_type, given_type, self.types):
                e = '%r is not a subclass of %r' % (new_type, given_type)
                raise CompileError(e, tree.meta)

    def store_field(self, tree):
        #unpack children for convenience
        obj, field, value = tree.children
        #convert field from token to string
        field = str(field)
        try:
            #attempt to get type of field from method table
            field_type = self.types[obj.type]['fields'][field]
        except KeyError:
            #fail if field was not found
            e = 'Could not find field %r of %r' % (field, obj.type)
            raise CompileError(e, tree.meta)

        #check whether this is an initial declaration in the constructor
        is_con = self.current_method == '$constructor'
        is_this = obj.data == 'var' and obj.children[0] == 'this'
        #if assignment is in constructor, modify type in method table
        if is_con and is_this:
            #find LCA of implied type and current type
            new_type = common_ancestor(value.type, field_type, self.types)
            #update method table and subtree with new type
            self.types[obj.type]['fields'][field] = new_type
            tree.type = new_type
        else:
            #get value of RHS of assignment
            imp_type = value.type
            #check type for compatibility with type from method table
            if not is_subclass(imp_type, field_type, self.types):
                e = '%r is not a subclass of %r' % (imp_type, field_type)
                raise CompileError(e, tree.meta)
            #update subtree with RHS type
            tree.type = imp_type

    def and_exp(self, tree):
        left, right = tree.children
        #check that both operands are Bools
        if left.type != 'Bool' or right.type != 'Bool':
            op = tree.data[:-4]
            e = 'Operands of %r must be Bool' % op
            raise CompileError(e, tree.meta)
        #the type of a logical expression is always Bool
        tree.type = 'Bool'
    or_exp = and_exp

    def condition(self, tree):
        #check that conditional has type Bool
        if tree.children[0].type != 'Bool':
            e = 'Type of condition must be Bool'
            raise CompileError(e, tree.meta)
        #the type of a condition is always Bool
        tree.type = 'Bool'

    def ternary(self, tree):
        #check that condition has type Bool
        cond, t_exp, f_exp = tree.children
        if cond.type != 'Bool':
            e = 'Type of condition must be Bool'
            raise CompileError(e, tree.meta)
        #the type of a ternary is the LCA of the possible RHS types
        tree.type = common_ancestor(t_exp.type, f_exp.type, self.types)

    def m_call(self, tree): #query the table for the return type
        left_type = tree.children[0].type #find type of receiver
        m_name = str(tree.children[1]) #get name of called function
        #retrieve parameter/return types of called function of receiver
        try:
            #attempt to retrieve information about method
            method = self.types[left_type]['methods'][m_name]
        except KeyError:
            #fail if method not found
            e = 'Could not find method %r of %r' % (m_name, left_type)
            raise CompileError(e, tree.meta)
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
                e = '%r expected %d arg%s, received %d' % e
                raise CompileError(e, tree.meta)

            #second check - check types of given arguments
            for rec, exp in zip(arg_types, exp_types):
                if not is_subclass(rec, exp, self.types):
                    e = (m_name, exp, rec)
                    e = '%r expected %r, received %r' % e
                    raise CompileError(e, tree.meta)
        tree.type = ret_type #set overall type of m_call node

    def c_call(self, tree):
        c_name = str(tree.children[0])
        try:
            class_ = self.types[c_name]
        except KeyError:
            #fail if class not found
            e = 'Could not find class %r' % (c_name)
            raise CompileError(e, tree.meta)
        else:
            args = tree.children[1].children
            #pluck types of given arguments
            arg_types = [child.type for child in args]
            #fetch types of expected arguments
            exp_types = class_['methods']['$constructor']['params']

            #first check - check number of given arguments
            if len(arg_types) != len(exp_types):
                #grammar!
                plural = 's' if len(exp_types) > 1 else ''
                e = (c_name, len(exp_types), plural, len(arg_types))
                e = '%r expected %d arg%s, received %d' % e
                raise CompileError(e, tree.meta)

            #second check - check types of given arguments
            for rec, exp in zip(arg_types, exp_types):
                if not is_subclass(rec, exp, self.types):
                    e = (c_name, exp, rec)
                    e = '%r expected %r, received %r' % e
                    raise CompileError(e, tree.meta)
        tree.type = c_name #set overall type of c_call node

    def ret_exp(self, tree):
        #type of the statement is type of the value
        tree.type = tree.children[0].type
        #extract return type of the current method
        try:
            current_class = self.types[self.current_class]
        except KeyError:
            #if the above access failed, this is the main class
            #the main class only has one method, the constructor
            #the constructor has a return type of Nothing
            ret_type = 'Nothing'
        else:
            current_method = current_class['methods'][self.current_method]
            ret_type = current_method['ret']
        #check that value's type is subclass of method's return type
        if not is_subclass(tree.type, ret_type, self.types):
            e = '%r must return %r, not %r'
            e = e % (self.current_method, ret_type, tree.type)
            raise CompileError(e, tree.meta)


#ensure that each type defines all instance methods declared in its superclass
#and that each inherited type is compatible with the type in the superclass
#ensure that overridden method signatures are compatible
def check_inherited(tree, types):
    classes = tree.children[0]
    #iterate over each user-defined class in the program
    for class_ in classes.children:
        c_name = str(class_.children[0].children[0])
        #the main class is not in the method table
        if c_name not in types:
            #skip the main class, as it has no fields or methods
            continue
        s_name = types[c_name]['super']

        #extract defined fields from both classes
        inherited = types[s_name]['fields']
        defined = types[c_name]['fields']
        #check each field in the superclass for compliance
        for field in inherited:
            try:
                #attempt to find the type of the field in this class
                sub_type = defined[field]
            except KeyError:
                e = '%r must define field %r' % (c_name, field)
                raise CompileError(e, class_.meta) from None
            else:
                #check that this class's field is a subtype of the super's
                sup_type = inherited[field]
                if not is_subclass(sub_type, sup_type, types):
                    e = "'%s.%s' (%r) must be a subtype of '%s.%s' (%r)"
                    e %= (c_name, field, sub_type, s_name, field, sup_type)
                    raise CompileError(e, class_.meta)

        methods = class_.children[1].children[0]
        #check methods for compatibility with superclass
        inherited = types[s_name]['methods']
        defined = types[c_name]['methods']
        #only check methods that are in the supertype and the subtype
        for method in methods.children:
            m_name = str(method.children[0])
            if m_name not in inherited:
                continue
            if m_name == '$constructor':
                continue
            sup_method = inherited[m_name]
            sub_method = defined[m_name]
            sup_params = sup_method['params']
            sub_params = sub_method['params']
            #check that the arguments have the same number of parameters
            if len(sup_params) != len(sub_params):
                e = '%s:%s must have the same number of arguments as %s:%s'
                e %= (c_name, m_name, s_name, m_name)
                raise CompileError(e, method.meta)
            #check that each argument of the supertype is a subclass
            #of the corresponding argument of the subtype
            for (sup_p, sub_p) in zip(sup_params, sub_params):
                if not is_subclass(sup_p, sub_p, types):
                    e = '%r is not compatible with %r in %s:%s'
                    e %= (sup_p, sub_p, c_name, m_name)
                    raise CompileError(e, method.meta)
            #check that the subtype returns a subclass of the supertype method
            sup_ret = sup_method['ret']
            sub_ret = sub_method['ret']
            if not is_subclass(sub_ret, sup_ret, types):
                e = 'Return type of %s:%s must be a subclass of %r'
                e %= (c_name, m_name, sup_ret)
                raise CompileError(e, method.meta)


#check if the first argument is a subclass of the second argument
def is_subclass(typ, sup, types):
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
