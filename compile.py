#!/usr/bin/python3

import lark
import argparse
import json
import sys
import itertools
from collections import defaultdict as dd

quack_grammar = """
    ?start: program

    ?program: statement*

    ?statement: r_exp ";"
              | assignment ";"
              | if_stmt
              | while_lp

    if_stmt: "if" condition block elifs else

    elifs: elif*

    elif: "elif" condition block

    else: ("else" block)?

    while_lp: "while" condition block

    condition: r_exp

    block: "{" statement* "}"
         | statement

    assignment: l_exp ":" type "=" r_exp -> assign
              | l_exp "=" r_exp          -> assign_imp

    ?type: NAME

    ?l_exp: NAME

    ?r_exp: expr
          | m_call

    m_call: r_exp "." m_name "(" m_args ")" -> m_call

    ?m_name: NAME

    m_args: r_exp ("," r_exp)* (",")?
          |

    ?expr: or_exp

    ?or_exp: and_exp
           | or_exp "or" and_exp -> or_exp

    ?and_exp: equality
            | and_exp "and" equality -> and_exp

    ?equality: comparison
             | equality "==" comparison -> equals
             | equality "!=" comparison -> notequals

    ?comparison: sum
               | comparison "<"  sum -> less
               | comparison "<=" sum -> atmost
               | comparison ">"  sum -> more
               | comparison ">=" sum -> atleast

    ?sum: product
        | sum "+" product -> plus
        | sum "-" product -> minus

    ?product: atom
            | product "*" atom -> times
            | product "/" atom -> divide

    ?atom: NUMBER      -> lit_number
         | "-" atom    -> neg
         | "not" atom    -> negate
         | l_exp       -> var
         | "(" expr ")"
         | boolean
         | nothing
         | string      -> lit_string

    ?boolean: "true"  -> lit_true
            | "false" -> lit_false
    
    ?nothing: "none"  -> lit_nothing
    
    ?string: ESCAPED_STRING

    %import common.NUMBER
    %import common.ESCAPED_STRING
    %import common.CNAME -> NAME
    %import common.WS_INLINE
    %import common.WS

    %ignore WS_INLINE
    %ignore WS
"""

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

#assigns a type to each node in the tree
class TypeInferrer(lark.visitors.Visitor_Recursive):
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
            if isinstance(left, lark.Token): #shouldn't be necessary
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

#generate assembly code from the parse tree
class Generator(lark.visitors.Visitor_Recursive):
    def __init__(self, code, types):
        #store the code array and types table
        super().__init__()
        self.code = code
        self.types = types
        self.variables = {} #stores names and types of local variables
        self.labels = dd(itertools.count) #stores count of label prefixes
    def emit(self, line, tab=True):
        #emits a line of code to the output array
        #adds a tab to the beginning by default
        if tab:
            self.code.append('\t' + line)
        else:
            self.code.append(line)
    def label(self, prefix):
        #generates a unique label name with the given prefix
        num = next(self.labels[prefix]) #get current number for given prefix
        return f'{prefix}_{num}'
    def visit(self, tree):
        #"and/or" expressions are handled differently
        if tree.data == 'and_exp':
            self.and_exp(tree)
        elif tree.data == 'or_exp':
            self.or_exp(tree)
        elif tree.data == 'if_stmt':
            self.if_stmt(tree)
        else:
            #most expressions are traversed postorder
            return super().visit(tree)
    def lit_number(self, tree):
        #push an integer onto the stack
        self.emit('const %s' % tree.children[0])
    def lit_true(self, tree):
        #push a boolean onto the stack
        self.emit('const true')
    def lit_false(self, tree):
        #push a boolean onto the stack
        self.emit('const false')
    def lit_nothing(self, tree):
        #push a nothing onto the stack
        self.emit('const nothing')
    def lit_string(self, tree):
        #push a string onto the stack
        self.emit('const %s' % tree.children[0])
    def var(self, tree):
        #load a local variable onto the stack
        self.emit('load %s' % tree.children[0])
    def assign(self, tree):
        #store the top value on the stack into a local variable
        name = tree.children[0]
        type = tree.children[1]
        #map the variable name to the type of the value
        self.variables[name] = type
        #emit a store instruction
        self.emit('store %s' % name)
    def assign_imp(self, tree):
        #store the top value on the stack into a local variable
        name = tree.children[0]
        type = tree.type
        #map the variable name to the type of the value
        self.variables[name] = type
        #emit a store instruction
        self.emit('store %s' % name)
    def m_call(self, tree):
        #emit a method call command and possibly a roll
        m_name = str(tree.children[1])
        #functions need to roll so that the receiver
        #is the first thing popped off the stack
        num_ops = len(tree.children[2].children)
        if num_ops: #don't roll for functions with no arguments
            self.emit('roll %d' % num_ops)
        left_type = tree.children[0].type
        #emit a method call of the correct type
        self.emit('call %s:%s' % (left_type, tree.children[1]))
    def and_exp(self, tree):
        left, right = tree.children
        #generate assembly for first expression, which will always run
        self.visit(left)
        #generate unique label names
        false_label = self.label('and')
        join_label = self.label('and')
        #if the first expression evaluates to false, jump to join point
        self.emit('jump_ifnot %s' % false_label)
        #generate assembly for second expression
        #this will only run if the first expression evaluated to true
        self.visit(right)
        #if the second expression evaluates to false, jump to join point
        self.emit('jump_ifnot %s' % false_label)
        #if neither jump was taken, push true as the result
        self.emit('const true')
        #skip past the join point
        self.emit('jump %s' % join_label)
        #join point: execution will come here if either expression is false
        self.emit('%s:' % false_label, False)
        #if either jump was taken, push false as the result
        self.emit('const false')
        #and expression is over - join point
        self.emit('%s:' % join_label, False)
    def or_exp(self, tree):
        left, right = tree.children
        #generate assembly for first expression, which will always run
        self.visit(left)
        #generate unique label names
        true_label = self.label('or')
        join_label = self.label('or')
        #if the first expression evaluates to true, jump to join point
        self.emit('jump_if %s' % true_label)
        #generate assembly for second expression
        #this will only run if the first expression evaluated to false
        self.visit(right)
        #if the second expression evaluates to true, jump to join point
        self.emit('jump_if %s' % true_label)
        #if neither jump was taken, push false as the result
        self.emit('const false')
        #skip past the join point
        self.emit('jump %s' % join_label)
        #join point: execution will come here if either expression is true
        self.emit('%s:' % true_label, False)
        #if either jump was taken, push true as the result
        self.emit('const true')
        #or expression is over - join point
        self.emit('%s:' % join_label, False)
    def if_stmt(self, tree):
        #unpack children nodes for convenience
        if_cond, if_block, elifs, _else = tree.children

        join_label = self.label('join') #generate join label - emitted at end
        #holds information about blocks after if-statement
        #used for generating labels
        meta = []
        for child in elifs.children:
            meta.append('elif') #add "elif" to meta for each elif block
        if _else.children:
            meta.append('else') #if else block exists, add "else" to meta
        labels = [self.label(i) for i in meta]

        #unconditionally evaluate the if statement's condition
        self.visit(if_cond)
        #emit the correct label to jump to if the condition was false
        if not labels:
            #if the if statement is alone, jump to the join point
            self.emit('jump_ifnot %s' % join_label)
        else:
            #if the if statement has friends, jump to the next condition
            self.emit('jump_ifnot %s' % labels[0])
        #if condition was true, execute the block
        self.visit(if_block)
        if labels:
            #jump past elif/else blocks to the join point
            self.emit('jump %s' % join_label)

        label_index = 0 #used to get current/next labels
        #generate code for elif blocks, if there are any
        for _elif in elifs.children:
            #unpack condition/block for convenience
            elif_cond, elif_block = _elif.children
            #get label that points to this block
            current_label = labels[label_index]
            label_index += 1
            #get label that will be jumped to if this block doesn't execute
            next_label = join_label if label_index == len(labels) else labels[label_index]

            #emit this block's label
            self.emit('%s:' % current_label, False)
            #evaluate the elif's condition
            self.visit(elif_cond)
            #jump to next block or join point if condition was false
            self.emit('jump_ifnot %s' % next_label)
            #execute block if condition was true
            self.visit(elif_block)
            #only jump to join if there is a block in between here and there
            if next_label != join_label:
                #jump past rest of the blocks after execution
                self.emit('jump %s' % join_label)

        #generate code for else block, if it exists
        if _else.children:
            #else label is always the last in labels
            else_label = labels[-1]
            #emit this block's label
            self.emit('%s:' % else_label, False)
            else_block = _else.children[0]
            #execute the else block
            self.visit(else_block)

        #emit the join label - this point will always be reached
        self.emit('%s:' % join_label, False)

#outputs assembly code to given stream
def generate_code(name, variables, code, out):
    emit = lambda s: print(s, file=out) #convenience method
    #emit header common to all files
    emit('.class %s:Obj\n\n.method $constructor' % name)
    if variables:
        #emit list of local variables separated by commas
        emit('.local %s' % ','.join(i for i in variables))
    emit('\tenter')
    #emit each line, indented by one tab
    for line in code:
        emit(line)
    #push return value of constructor
    emit('\tconst nothing')
    #return, popping zero arguments
    emit('\treturn 0')

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

#read an input and output file from the command line arguments
def cli_parser():
    parser = argparse.ArgumentParser(prog='translate')
    parser.add_argument('source', type=argparse.FileType('r'))
    parser.add_argument('target', nargs='?',
                        type=argparse.FileType('w'), default=sys.stdout)
    parser.add_argument('--name', nargs='?', default='Main')
    parser.add_argument('--tree', '-t', action='store_true')
    return parser.parse_args()

def main():
    args = cli_parser()
    #read type table from file
    with open('builtin_methods.json', 'r') as f:
        types = json.load(f)
    parser = lark.Lark(
        quack_grammar,
        parser='lalr'
    )
    
    #create initial parse tree
    tree = parser.parse(args.source.read())

    if args.tree:
        print(tree.pretty())
        return

    #desugar binary operators
    transformer = Transformer()
    tree = transformer.transform(tree)

    #decorate tree with types
    inferrer = TypeInferrer(types);
    inferrer.visit(tree)

    #fill code array with assembly instructions
    code = []
    generator = Generator(code, types)
    generator.visit(tree)

    #output code to file or stdout
    generate_code(args.name, generator.variables, code, args.target)

if __name__ == '__main__' and not sys.flags.interactive:
    main()
