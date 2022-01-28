#!/usr/bin/python3

import lark
import argparse
import json
import sys

#this grammar was created during office hours on 1/19/22
quack_grammar = """
    ?start: program

    ?program: statement*

    ?statement: r_exp ";"
              | assignment ";"

    assignment: l_exp ":" type "=" r_exp -> assign

    ?type: NAME

    ?l_exp: NAME

    ?r_exp: sum
          | m_call

    m_call: r_exp "." m_name "(" m_args ")" -> m_call

    ?m_name: NAME

    ?m_args: r_exp ("," r_exp)* (",")?
           |

    ?sum: product
        | sum "+" product -> plus
        | sum "-" product -> minus

    ?product: atom
            | product "*" atom -> mul
            | product "/" atom -> div

    ?atom: NUMBER      -> lit_number
         | "-" atom    -> neg
         | l_exp       -> var
         | "(" sum ")"
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

#operates on the tree as it is created
#desugars binary operators into method calls
@lark.v_args(tree=True)
class Transformer(lark.Transformer):
    def plus(self, tree): #desugar "a + b" into "a.PLUS(b)"
        return self.op(tree, 'PLUS')
    def minus(self, tree): #desugar "a - b" into "a.MINUS(b)"
        return self.op(tree, 'MINUS')
    def mul(self, tree): #desugar "a * b" into "a.TIMES(b)"
        return self.op(tree, 'TIMES')
    def div(self, tree): #desugar "a / b" into "a.DIVIDE(b)"
        return self.op(tree, 'DIVIDE')
    def neg(self, tree): #desugar "-a" into "a.NEG()"
        return self.op(tree, 'NEG')
    #create a method call subtree with the appropriate binary op function
    def op(self, tree, op):
        children = [
            tree.children[0], #receiver object
            op, #name of operator
            lark.Tree('m_args', tree.children[1:]) #argument object, if provided
        ]
        return lark.Tree('m_call', children)

#assigns a type to each node in the tree
class TypeInferrer(lark.visitors.Visitor_Recursive):
    def __init__(self, types):
        self.variables = {} #set to store types of initialized variables
        self.types = types #method tables - used to find return values
    def __default__(self, tree):
        literals = { #map between node names and builtin type names
            'lit_number': 'Int',
            'lit_string': 'String',
            'lit_true': 'Boolean',
            'lit_false': 'Boolean',
            'lit_nothing': 'Nothing'
        }
        if tree.data in literals: #assign builtin type for literal token
            tree.type = literals[tree.data]
        elif tree.data == 'var': #search variables map for assigned type
            name = str(tree.children[0])
            tree.type = self.variables[name]
        elif tree.data == 'assign': #map the variable name to the given type
            left = tree.children[0]
            tree.type = tree.children[1]
            if isinstance(left, lark.Token): #shouldn't be necessary
                self.variables[str(left)] = tree.type
        elif tree.data == 'm_call': #query the table for the return type
            left_type = tree.children[0].type #find type of receiver
            m_name = tree.children[1] #get name of called function
            #retrieve return type of called function of receiver
            ret = self.types[left_type]['methods'][m_name]['ret']
            tree.type = ret

#generate assembly code from the parse tree
class Generator(lark.visitors.Visitor_Recursive):
    def __init__(self, code, types):
        #store the code array and types table
        super().__init__()
        self.code = code
        self.types = types
        self.variables = {} #stores names and types of local variables
    def lit_number(self, tree):
        #push an integer onto the stack
        self.code.append('const %s' % tree.children[0])
    def lit_true(self, tree):
        #push a boolean onto the stack
        self.code.append('const true')
    def lit_false(self, tree):
        #push a boolean onto the stack
        self.code.append('const false')
    def lit_nothing(self, tree):
        #push a nothing onto the stack
        self.code.append('const nothing')
    def lit_string(self, tree):
        #push a string onto the stack
        self.code.append('const %s' % tree.children[0])
    def var(self, tree):
        #load a local variable onto the stack
        self.code.append('load %s' % tree.children[0])
    def assign(self, tree):
        #store the top value on the stack into a local variable
        name = tree.children[0]
        type = tree.children[1]
        #map the variable name to the type of the value
        self.variables[name] = type
        self.code.append('store %s' % name)
    def m_call(self, tree):
        #emit a method call command and possibly a roll
        m_name = str(tree.children[1])
        #arithmetic operators need to roll so that the receiver
        #is the first thing popped off the stack
        if m_name in ('PLUS', 'MINUS', 'TIMES', 'DIVIDE'):
            self.code.append('roll 1') #all binary ops have two args
        left_type = tree.children[0].type
        #emit a method call of the correct type
        self.code.append('call %s:%s' % (left_type, tree.children[1]))

def generate_code(name, variables, code, out):
    emit = lambda s: print(s, file=out)
    emit('.class %s:Obj\n\n.method $constructor' % name)
    if variables:
        emit('.local %s' % ','.join(i for i in variables))
    emit('\tenter')
    for line in code:
        emit('\t' + line)
    emit('\tconst nothing')
    emit('\treturn 0')

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
    with open('builtin_methods.json', 'r') as f:
        types = json.load(f)
    parser = lark.Lark(
        quack_grammar,
        parser='lalr'
    )
    
    tree = parser.parse(args.source.read())

    transformer = Transformer()
    tree = transformer.transform(tree)

    inferrer = TypeInferrer(types);
    inferrer.visit(tree)

    code = []
    generator = Generator(code, types)
    generator.visit(tree)

    generate_code(args.name, generator.variables, code, args.target)

if __name__ == '__main__' and not sys.flags.interactive:
    main()
