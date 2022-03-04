import lark
from lark import Tree
from copy import deepcopy
from compiler.errors import CompileError


#loads user-defined classes into the method table
def load_classes(tree, types):
    classes = tree.children[0]
    for class_ in classes.children:
        #unpack children for convenience
        class_sig, class_body = class_.children
        #extract class name
        c_name = str(class_sig.children[0])

        formal_args = class_sig.children[1]
        #get formal argument types for the constructor
        arg_types = [str(arg.children[1]) for arg in formal_args.children]

        #extract superclass's name - Obj if none is given
        super_type = str(class_sig.children[2] or 'Obj')
        #retrieve information about superclass from method table
        super_class = types[super_type]
        #make a copy of the superclass's methods for this table
        super_methods = deepcopy(super_class['methods'])
        #make a copy of the superclass's fields for this table
        super_fields = deepcopy(super_class['fields'])

        #initialize this class's entry in the method table
        types[c_name] = {
            'super': super_type,
            'methods': super_methods,
            'fields': super_fields
        }

        #unpack children for convenience
        constructor, methods = class_body.children
        #create subtree for the constructor method
        con_method = Tree('method', [
            '$constructor',
            formal_args,
            'Nothing',
            Tree('statement_block', constructor.children)
        ])

        #add constructor method to class's methods
        methods.children.insert(0, con_method)

        #iterate over user-defined methods
        for method in methods.children:
            #extract method name from AST
            m_name = str(method.children[0])
            formal_args = method.children[1]
            #get formal argument types for the method
            arg_types = [str(arg.children[1]) for arg in formal_args.children]
            #extract return type of function
            #if return type is not given, infer that function returns 'none'
            ret_type = str(method.children[2] or 'Nothing')

            #add (or update) user-defined method to method table
            types[c_name]['methods'][m_name] = {
                'params': arg_types,
                'ret': ret_type
            }

        #remove constructor child of class, as the constructor was added
        #to the methods block
        class_body.children.pop(0)


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
