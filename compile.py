#!/usr/bin/python3

import lark
import argparse
import sys

#this grammar was created during office hours on 1/19/22
quack_grammar = """
    ?start: program

    ?program: statement*

    ?statement: r_exp ";"
              | assignment ";"

    assignment: l_exp ":" type "=" r_exp

    ?type: NAME

    ?l_exp: NAME

    ?r_exp: sum
          | m_call

    m_call: r_exp "." m_name "(" m_args ")"

    ?m_name: NAME

    ?m_args: r_exp ("," r_exp)* (",")?
           |

    ?sum: product
        | sum "+" product -> plus
        | sum "-" product -> minus

    ?product: atom
            | product "*" atom -> mul
            | product "/" atom -> div

    ?atom: NUMBER -> number
         | "-" atom
         | l_exp
         | "(" sum ")"
         | boolean
         | nothing
         | string

    boolean: "true"
           | "false"
    
    nothing: "none"
    
    string: ESCAPED_STRING

    %import common.NUMBER
    %import common.ESCAPED_STRING
    %import common.CNAME -> NAME
    %import common.WS_INLINE
    %import common.WS

    %ignore WS_INLINE
    %ignore WS
"""

#operates on the tree as it is created
@lark.v_args(tree=True)
class Transformer(lark.Transformer):
    def plus(self, tree):
        children = [
            tree.children[0],
            'PLUS',
            lark.Tree('m_args', tree.children[1:])
        ]
        return lark.Tree('m_call', children)
    def minus(self, tree):
        children = [
            tree.children[0],
            'MINUS',
            lark.Tree('m_args', tree.children[1:])
        ]
        return lark.Tree('m_call', children)
    def mul(self, tree):
        children = [
            tree.children[0],
            'TIMES',
            lark.Tree('m_args', tree.children[1:])
        ]
        return lark.Tree('m_call', children)
    def div(self, tree):
        children = [
            tree.children[0],
            'DIVIDE',
            lark.Tree('m_args', tree.children[1:])
        ]
        return lark.Tree('m_call', children)

class Generator(lark.visitors.Visitor_Recursive):
    def number(*args):
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

def main():
    args = cli_parser()
    parser = lark.Lark(
        quack_grammar,
        parser='lalr'
    )
    
    tree = parser.parse(args.source.read())
    #print(tree)
    transformer = Transformer()
    tree = transformer.transform(tree)
    #print(tree.pretty())
    generator = Generator()
    generator.visit(tree)

if __name__ == '__main__' and not sys.flags.interactive:
    main()
