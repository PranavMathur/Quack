import lark
from compiler.errors import CompileError

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
        #handle if statements and while loops
        if tree.data == 'if_stmt':
            self._if_stmt(tree)
        elif tree.data == 'while_lp':
            self._while_lp(tree)
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
        #compute intersectin of all new variable sets
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
    def __default__(self, tree):
        if tree.data == 'var':
            #check that variable name exists in the variables set
            name = str(tree.children[0])
            if name not in self.variables:
                #fail if variable is not found
                e = 'Variable %r is not defined' % name
                raise CompileError(e)
        elif tree.data == 'assign':
            #add variable name to variables set
            name = str(tree.children[0])
            self.variables.add(name)
