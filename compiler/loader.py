import lark
from lark import Tree
from copy import deepcopy
from compiler.errors import CompileError


#loads user-defined classes into the method table
class ClassLoader(lark.visitors.Visitor_Recursive):
    def __init__(self, types):
        self.types = types #method table

    def class_(self, tree):
        #unpack children for convenience
        class_sig, class_body = tree.children
        #extract class name
        c_name = str(class_sig.children[0])

        formal_args = class_sig.children[1]
        #get formal argument types for the constructor
        arg_types = [str(arg.children[1]) for arg in formal_args.children]
        #extract superclass's name - Obj if none is given

        super_type = str(class_sig.children[2] or 'Obj')
        #retrieve information about superclass from method table
        super_class = self.types[super_type]
        #make a copy of the superclass's methods for this table
        super_methods = deepcopy(super_class['methods'])
        #make a copy of the superclass's fields for this table
        super_fields = deepcopy(super_class['fields'])

        #initialize this class's entry in the method table
        self.types[c_name] = {
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

        #manually set argument/return types for the constructor
        con_method.m_name = '$constructor'
        con_method.arg_types = arg_types
        con_method.ret_type = 'Nothing'
        #add constructor method to class's methods
        methods.children.insert(0, con_method)

        #iterate over user-defined methods
        for method in methods.children:
            #add (or update) user-defined method to method table
            self.types[c_name]['methods'][method.m_name] = {
                'params': method.arg_types,
                'ret': method.ret_type
            }
        #remove constructor child of class, as the constructor was added
        #to the methods block
        class_body.children.pop(0)

    #infer the type of a user-defined method
    def method(self, tree):
        #extract method name from AST
        tree.m_name = str(tree.children[0])
        formal_args = tree.children[1]
        #get formal argument types for the method
        tree.arg_types = [str(arg.children[1]) for arg in formal_args.children]
        #extract return type of function
        #if return type is not given, infer that function returns 'none'
        tree.ret_type = str(tree.children[2] or 'Nothing')


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
                raise CompileError(e)

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
                raise CompileError(e)
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
