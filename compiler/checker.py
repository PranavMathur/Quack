import lark
from lark import Tree
from compiler.errors import CompileError


#determines what fields are defined in a class's constructor
#and ensures no fields were only defined on some paths
class FieldLoader(lark.visitors.Visitor_Recursive):
    def __init__(self, types):
        #will be updated after each class is processed
        self.types = types
        #stores variables that have definitely been initialized
        self.initialized = set()
        #stores variables that may have been initialized
        self.seen = set()
        #store current method name to check whether we are in the constructor
        self.current_method = ''

    def visit(self, tree):
        #store current method name
        if tree.data == 'method':
            self.current_method = str(tree.children[0])

        #handle if statements and while loops
        if tree.data == 'if_stmt':
            self._if_stmt(tree)
        elif tree.data == 'while_lp':
            self._while_lp(tree)
        elif tree.data == 'typecase':
            self._typecase(tree)
        else:
            #handle everything else (stores and loads)
            for child in tree.children:
                if isinstance(child, lark.Tree):
                    self.visit(child)
            self._call_userfunc(tree)

        #if the entire class has been processed, check for uninitialized
        #fields and update the types table
        if tree.data == 'class_':
            #compute the fields which were seen but not initialized
            free_fields = self.seen - self.initialized
            if free_fields:
                #if any such fields were found, throw a compile error
                s = ', '.join(free_fields)
                word = 'are' if len(free_fields) > 1 else 'is'
                e = '%r %s not defined on all paths' % (s, word)
                raise CompileError(e, tree.meta)

            #find the name of the current class
            class_ = tree.children[0].children[0]
            fields = self.types[class_]['fields']

            #store each new field in the types table
            for field in self.initialized:
                if field not in fields:
                    fields[field] = ''

            #reset the initialized and seen sets for the next class
            self.initialized = set()
            self.seen = set()

    def _if_stmt(self, tree):
        #unpack children for convenience
        if_cond, if_block, elifs, _else = tree.children

        #check if condition with master fields set
        self.visit(if_cond)

        #used to store sets of fields found in each block
        field_sets = []
        #store master fields set before checking if block
        old_init = self.initialized
        #make a copy of the master fields set for use in the if block
        self.initialized = old_init.copy()

        #check the if block for compliance
        self.visit(if_block)
        #add state of fields set after if block to list of sets
        field_sets.append(self.initialized)
        #reset state of master fields set
        self.initialized = old_init

        #check condition and block for every elif
        for _elif in elifs.children:
            #unpack children for convenience
            elif_cond, elif_block = _elif.children
            #check elif condition with master fields set
            self.visit(elif_cond)
            #make a copy of the master fields set for use in the elif block
            self.initialized = old_init.copy()

            #check the elif block for compliance
            self.visit(elif_block)
            #add state of fields set after elif block to list of sets
            field_sets.append(self.initialized)
            #reset state of master fields set
            self.initialized = old_init

        #if there is an else block, check it for compliance
        if _else.children:
            else_block = _else.children[0]
            #make a copy of the master fields set for use in the else block
            self.initialized = old_init.copy()
            #check the else block for compliance

            self.visit(else_block)
            #add state of fields set after else block to list of sets
            field_sets.append(self.initialized)
            #reset state of master fields set
            self.initialized = old_init
        else:
            #if there is no else block, pretend it added no new fields
            field_sets.append(self.initialized)

        #compute intersection of all new field sets
        new_fields = field_sets[0].intersection(*field_sets)
        #update the master fields set with the new fields
        self.initialized.update(new_fields)

    def _while_lp(self, tree):
        #unpack children for convenience
        condition, block = tree.children
        #check while condition for compliance
        self.visit(condition)

        #store master fields set before checking while block
        old_init = self.initialized
        #make a copy of the master fields set for use in the while block
        self.initialized = old_init.copy()
        #check while block for compliance
        self.visit(block)
        #reset state of master fields set
        self.initialized = old_init

    def _typecase(self, tree):
        #unpack children for convenience
        expr, alts = tree.children

        #check typecase expression for compliance
        self.visit(expr)

        #used to store sets of fields found in each alternative
        field_sets = []
        #store master fields set before checking alternatives
        old_init = self.initialized

        #store whether or not a default alternative exists
        #if there is an alternative with the type Obj,
        #we know that flow will travel to one of the alternatives
        has_obj = False
        #iterate over the alternatives
        for alt in alts.children:
            #unpack children for convenience
            name, type, block = alt.children
            if type == 'Obj':
                has_obj = True
            #make copy of master set for checking this alternative
            self.initialized = old_init.copy()
            self.visit(block)

            #store the new set of defined variables
            field_sets.append(self.initialized)
            #reset variables to the master set
            self.initialized = old_init

        #if there is not Obj branch, pretend there was an empty branch
        #that declared no new variables
        if not has_obj:
            field_sets.append(self.initialized)

        #compute intersection of all new variable sets
        new_vars = field_sets[0].intersection(*field_sets)
        #update the master variables set with the new variables
        self.initialized.update(new_vars)

    def __default__(self, tree):
        #only allow new fields to be defined in the constructor
        if self.current_method != '$constructor':
            return

        if tree.data == 'load_field':
            obj = tree.children[0]
            #only process stores from the "this" object
            if (not isinstance(obj, Tree)
                    or obj.data != 'var'
                    or str(obj.children[0]) != 'this'):
                return

            #get the name of the loaded field
            field = str(tree.children[1])
            #check that the field name exists in the initialized set
            if field not in self.initialized:
                e = 'Field %r is not defined' % field
                raise CompileError(e, tree.meta)
            #keep track of fields we have loaded at any point
            self.seen.add(field)
        elif tree.data == 'store_field':
            obj = tree.children[0]
            #only process stores to the "this" object
            if (not isinstance(obj, Tree)
                    or obj.data != 'var'
                    or str(obj.children[0]) != 'this'):
                return

            #get the name of the stored field
            field = str(tree.children[1])
            #this field has been initialized on this path
            self.initialized.add(field)
            #this field has been initialized on some path
            self.seen.add(field)


#ensures each method has a return statement on every path
class ReturnChecker(lark.visitors.Visitor_Recursive):
    def visit(self, tree):
        #if and while are handled specially
        if tree.data == 'if_stmt':
            return self._if_stmt(tree)
        elif tree.data == 'while_lp':
            return self._while_lp(tree)
        elif tree.data == 'typecase':
            return self._typecase(tree)
        else:
            #check for a return in any subtree of this tree
            has_return = False
            for child in tree.children:
                if isinstance(child, lark.Tree):
                    ret = self.visit(child)
                    has_return = has_return or ret
            ret = self._call_userfunc(tree)
            return has_return or ret

    def method(self, tree):
        #extract statements from subtree
        statements = tree.children[3].children
        for statement in statements:
            #if any top-level statement in the block passes the test,
            #then the flow of execution will definitely hit a return
            if self.visit(statement):
                #the else clause will only execute if this break never does
                break
        else:
            #there exists a path without a return statement
            m_name = str(tree.children[0])
            ret_type = str(tree.children[2] or 'Nothing')
            if ret_type != 'Nothing':
                e = '%r does not return on every path' % m_name
                raise CompileError(e, tree.meta)
            nothing = Tree('lit_nothing', [])
            ret_node = Tree('ret_exp', [nothing])
            statements.append(ret_node)

    def ret_exp(self, tree):
        #a return expression is trivially true
        #if flow reaches this statement, the method will return
        return True

    def _if_stmt(self, tree):
        if_cond, if_block, elifs, _else = tree.children
        #first check - if the main block does not return, the entire block fails
        if not self.visit(if_block):
            return False
        #second check - if there are any elifs, each must pass the check
        for _elif in elifs.children:
            elif_cond, elif_block = _elif.children
            if not self.visit(elif_block):
                return False
        #last check - if there is no else, fail immediately
        #otherwise, the else must pass the check
        if _else.children:
            else_block = _else.children[0]
            if not self.visit(else_block):
                return False
        else:
            return False
        #flow will only reach this point if all above checks passed
        return True

    def _while_lp(self, tree):
        #a while loop is never guaranteed to execute, so it always fails
        return False

    def _typecase(self, tree):
        expr, alts = tree.children
        has_obj = False
        for alt in alts.children:
            name, type, block = alt.children
            if type == 'Obj':
                has_obj = True
            #if any alternative does not have a return,
            #then the typecase does not have a return
            if not self.visit(block):
                return False
        #if every alternative has a return, then the typecase has a return
        #if there was a default alternative
        return has_obj

    def __default__(self, tree):
        #most statements are not ret_exps, so they do not guarantee a return
        return False


#checks that variables are always defined before use
class VarChecker(lark.visitors.Visitor_Recursive):
    def __init__(self):
        #store the set of variables currently in scope
        self.variables = set()

    def visit(self, tree):
        #reset the set of seen variables at the beginning of each method
        if tree.data == 'method':
            #"this" is available in any method
            self.variables = {'this'}
            #extract formal_args node from subtree
            formal_args = tree.children[1].children
            #iterate over formal parameters
            for arg in formal_args:
                #extract name and type from formal parameter
                name, type = arg.children
                #add name of parameter to variables set
                self.variables.add(str(name))

        #handle if statements and while loops
        if tree.data == 'if_stmt':
            self._if_stmt(tree)
        elif tree.data == 'while_lp':
            self._while_lp(tree)
        elif tree.data == 'typecase':
            self._typecase(tree)
        else:
            #handle everything else (assignments and references)
            for child in tree.children:
                if isinstance(child, lark.Tree):
                    self.visit(child)
            return self._call_userfunc(tree)

    #check each condition/block of the if statement individually and
    #add variables declared in all possible paths to master variables set
    def _if_stmt(self, tree):
        #unpack children for convenience
        if_cond, if_block, elifs, _else = tree.children

        #check if condition with master variables set
        self.visit(if_cond)

        #used to store sets of variables found in each block
        var_sets = []
        #store master variables set before checking if block
        old_variables = self.variables
        #make a copy of the master variables set for use in the if block
        self.variables = old_variables.copy()

        #check the if block for compliance
        self.visit(if_block)
        #add state of variables set after if block to list of sets
        var_sets.append(self.variables)
        #reset state of master variables set
        self.variables = old_variables

        #check condition and block for every elif
        for _elif in elifs.children:
            #unpack children for convenience
            elif_cond, elif_block = _elif.children
            #check elif condition with master variables set
            self.visit(elif_cond)
            #make a copy of the master variables set for use in the elif block
            self.variables = old_variables.copy()

            #check the elif block for compliance
            self.visit(elif_block)
            #add state of variables set after elif block to list of sets
            var_sets.append(self.variables)
            #reset state of master variables set
            self.variables = old_variables

        #if there is an else block, check it for compliance
        if _else.children:
            else_block = _else.children[0]
            #make a copy of the master variables set for use in the else block
            self.variables = old_variables.copy()

            #check the else block for compliance
            self.visit(else_block)
            #add state of variables set after else block to list of sets
            var_sets.append(self.variables)
            #reset state of master variables set
            self.variables = old_variables
        else:
            #if there is no else block, pretend it added no new variables
            var_sets.append(self.variables)

        #compute intersection of all new variable sets
        new_vars = var_sets[0].intersection(*var_sets)
        #update the master variables set with the new variables
        self.variables.update(new_vars)

    def _while_lp(self, tree):
        #unpack children for convenience
        condition, block = tree.children

        #check while condition for compliance
        self.visit(condition)
        #store master variables set before checking while block
        old_variables = self.variables
        #make a copy of the master variables set for use in the while block
        self.variables = old_variables.copy()

        #check while block for compliance
        self.visit(block)
        #reset state of master variables set
        self.variables = old_variables

    def _typecase(self, tree):
        #unpack children for convenience
        expr, alts = tree.children

        #check typecase expression for compliance
        self.visit(expr)

        #used to store sets of variables found in each alternative
        var_sets = []
        #store master variables set before checking alternatives
        old_variables = self.variables

        #store whether or not a default alternative exists
        #if there is an alternative with the type Obj,
        #we know that flow will travel to one of the alternatives
        has_obj = False
        #iterate over the alternatives
        for alt in alts.children:
            #unpack children for convenience
            name, type, block = alt.children
            if type == 'Obj':
                has_obj = True
            #make copy of master set for checking this alternative
            self.variables = old_variables.copy()
            #add the new typecase variable
            self.variables.add(name)
            self.visit(block)

            #store the new set of defined variables
            var_sets.append(self.variables)
            #reset variables to the master set
            self.variables = old_variables

        #if there is not Obj branch, pretend there was an empty branch
        #that declared no new variables
        if not has_obj:
            var_sets.append(self.variables)

        #compute intersection of all new variable sets
        new_vars = var_sets[0].intersection(*var_sets)
        #update the master variables set with the new variables
        self.variables.update(new_vars)

    def __default__(self, tree):
        if tree.data == 'var':
            #check that variable name exists in the variables set
            name = str(tree.children[0])
            if name not in self.variables:
                #fail if variable is not found
                e = 'Variable %r is not defined' % name
                raise CompileError(e, tree.meta)
        elif tree.data == 'assign':
            #add variable name to variables set
            name = str(tree.children[0])
            self.variables.add(name)
