#!/usr/bin/python3

import lark
import argparse
import json
import sys

from compiler.transformer import Transformer
from compiler.typechecker import TypeChecker
from compiler.generator import Generator, generate_code

quack_grammar = """
//the start symbol is start, which consists of a program
?start: program

//a program can have zero or more statements
?program: statement*

//a statement can be a right expression, an assignment,
//an if statement, or a while loop
?statement: r_exp ";"
          | assignment ";"
          | if_stmt
          | while_lp

//an if statement consists of a condition, an execution block,
//zero or more elif statements, and an optional else statement
if_stmt: "if" condition block elifs else

//collection of zero or more elif statements
//useful to have elifs grouped during code generation
elifs: elif*

//an elif statement consists of a condition and an execution block
elif: "elif" condition block

//an else statement may consist of an execution block
else: ("else" block)?

//a while loop consists of a condition and an execution block
while_lp: "while" condition block

//a condition is a right expression
//the type checker will ensure that this evaluates to a boolean
condition: r_exp

//a block may be a collegtion of statements within braces
//or a single statement
block: "{" statement* "}"
     | statement

//an assignment may have an explicit type given, or it may be inferred
assignment: l_exp ":" type "=" r_exp -> assign
          | l_exp "=" r_exp          -> assign_imp

//a type is an identifier
?type: NAME

//a left expression is a variable name
?l_exp: NAME

//a right expression is an expression or a method call
?r_exp: expr
      | m_call

//a method call is a right expression, a method name, and zero or more arguments
m_call: r_exp "." m_name "(" m_args ")" -> m_call

//a method name is an identifier
?m_name: NAME

//a method argument is a right expression
//zero or more arguments may be given
//a trailing comma is allowed
m_args: r_exp ("," r_exp)* (",")?
      |

//an expression can be a combination of the following
//combination of nonterminals
//the following nonterminals are ordered from lowest to highest precedence
?expr: or_exp

//"or" binds less tightly than "and" and is left-associative
?or_exp: and_exp
       | or_exp "or" and_exp -> or_exp

//"and" binds less tightly than equality and is left-associative
?and_exp: equality
        | and_exp "and" equality -> and_exp

//equality binds less tightly than comparison and is left-associative
?equality: comparison
         | equality "==" comparison -> equals
         | equality "!=" comparison -> notequals

//comparison binds less tightly than addition and is left-associative
?comparison: sum
           | comparison "<"  sum -> less
           | comparison "<=" sum -> atmost
           | comparison ">"  sum -> more
           | comparison ">=" sum -> atleast

//addition and subtraction bind less tightly
//than multiplication and is left-associative
?sum: product
    | sum "+" product -> plus
    | sum "-" product -> minus

//multiplication and division are the highest precedence binary operations,
//but bind less tightly than unary operators, literals,
//and parenthesized expressions
?product: atom
        | product "*" atom -> times
        | product "/" atom -> divide

//an atom can be a literal, a unary operation on an atom,
//or a parenthesized expression
?atom: NUMBER       -> lit_number
     | "-" atom     -> neg
     | "not" atom   -> negate
     | l_exp        -> var
     | "(" expr ")"
     | boolean
     | nothing
     | string       -> lit_string

//a boolean can be a literal true or false
?boolean: "true"  -> lit_true
        | "false" -> lit_false

//a "nothing" object can only be a literal "none"
?nothing: "none"  -> lit_nothing

//strings are predefined by lark
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
