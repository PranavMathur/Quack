#!/usr/bin/python3

import lark
import argparse
import json
import sys

from compiler.transformer import Transformer
from compiler.typechecker import TypeChecker
from compiler.generator import Generator, generate_code

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
    type_checker = TypeChecker(types)
    type_checker.visit(tree)

    #fill code array with assembly instructions
    code = []
    generator = Generator(code, types)
    generator.visit(tree)

    #output code to file or stdout
    generate_code(args.name, generator.variables, code, args.target)

if __name__ == '__main__' and not sys.flags.interactive:
    main()
