#!/usr/bin/python3

import lark
import argparse
import sys

#this grammar was created during office hours on 1/19/22
quack_grammar = """
    ?start: program

    program: statement
           | program statement

    statement: r_exp ";"
             | assignment ";"

    assignment: l_exp ":" type "=" r_exp -> assign

    type: NAME

    l_exp: NAME

    r_exp: sum
         | m_call

    m_call: r_exp "." m_name "(" m_args ")"

    m_name: NAME

    m_args: r_exp ("," r_exp)* (",")?
          |

    sum: product
       | sum "+" product   -> add
       | sum "-" product   -> sub

    product: atom
           | product "*" atom  -> mul
           | product "/" atom  -> div

    atom: NUMBER           -> number
        | "-" atom         -> neg
        | l_exp            -> var
        | "(" sum ")"
        | boolean
        | nothing
        | string

    boolean: "true"        -> lit_true
           | "false"       -> lit_false
    
    nothing: "none"        -> lit_nothing
    
    string: ESCAPED_STRING -> string

    %import common.NUMBER
    %import common.ESCAPED_STRING
    %import common.CNAME -> NAME
    %import common.WS_INLINE
    %import common.WS

    %ignore WS_INLINE
    %ignore WS
"""

#operates on the tree as it is created
@lark.v_args(inline=True)
class Transformer(lark.Transformer):
    def __init__(self, output):
        self.variables = dict()
        self.output = output
    def number(self, token):
        #if a number is found, output a "push constant" command
        self.output.append('\tconst %s' % token)
    def lit_true(self):
        self.output.append('\tconst true')
    def lit_false(self):
        self.output.append('\tconst false')
    def lit_nothing(self):
        self.output.append('\tconst nothing')
    def string(self, token):
        self.output.append('\tconst %s' % token)
    def add(self, a, b):
        #output a call to the builtin addition function
        self.output.append('\tcall Int:plus')
    def sub(self, a, b):
        #output a call to the builtin subtraction function
        self.output.append('\tcall Int:sub')
    def mul(self, a, b):
        #output a call to the builtin multiplication function
        self.output.append('\tcall Int:mult')
    def div(self, a, b):
        #output a call to the builtin division function
        self.output.append('\tcall Int:div')
    def neg(self, a): #
        #output a call to the builtin negation function
        self.output.append('\tcall Int:neg')
    def assign(self, name, type, value):
        self.variables[str(name)] = str(type)
        self.output.append('\tstore %s' % name)
    def var(self, name):
        self.output.append('\tload %s' % name)
    def call(*args):
        print(args)

#read an input and output file from the command line arguments
def cli_parser():
    parser = argparse.ArgumentParser(prog='translate')
    parser.add_argument('source', type=argparse.FileType('r'))
    parser.add_argument('target', nargs='?',
                        type=argparse.FileType('w'), default=sys.stdout)
    parser.add_argument('--name', nargs='?', default='Main')
    parser.add_argument('--tree', '-t', action='store_true')
    return parser.parse_args()

assembly_header = """\
.class %s:Obj

.method $constructor\
"""

def main():
    args = cli_parser()
    output = []
    transformer = Transformer(output)
    if args.tree:
        transformer = None
    parser = lark.Lark(
        quack_grammar,
        parser='lalr',
        transformer=transformer
    )
    gen = output.append
    
    gen(assembly_header % args.name) #output header of assembly file
    gen('')
    #iterate through arithmetic expressions
    for line in args.source:
        line = line.strip() #remove extraneous whitespace
        if not line: #ignore blank lines
            continue
        #output command to print raw expression
        gen('\tconst "%s\\n"' % line.replace('"', "'"))
        gen('\tcall String:print')
        gen('\tpop')

        try:
            #attempt to parse expression
            tree = parser.parse(line)
            if args.tree:
                print(tree.pretty())
        except lark.exceptions.LarkError as e:
            raise e from None
            #output to stderr on failed parse
            print('Invalid line: "%s"' % line, file=sys.stderr)
    
    if args.tree:
        return

    gen('\tconst "---------------\\n"')
    gen('\tcall String:print')
    gen('\tpop')

    variables = transformer.variables
    for variable in variables:
        gen('\tconst "%s = "' % variable)
        gen('\tcall String:print')
        gen('\tpop')
        gen('\tload %s' % variable)
        gen('\tcall Obj:print')
        gen('\tpop')
        gen('\tconst "\\n"')
        gen('\tcall String:print')
        gen('\tpop')
    
    #end of method
    gen('\treturn 0')

    if variables:
        output[1] = '.local %s' % ','.join(i for i in variables)

    for line in output:
        if line:
            print(line, file=args.target)

if __name__ == '__main__' and not sys.flags.interactive:
    main()
