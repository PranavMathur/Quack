#!/usr/bin/python3

import lark
import argparse
import json
import sys

from compiler.grammar import quack_grammar
from compiler.generator import Generator, generate_code
from compiler.transformer import Transformer
from compiler.typechecker import TypeChecker

types_file = 'builtin_methods.json'

#read an input and output file from the command line arguments
def cli_parser():
    parser = argparse.ArgumentParser(prog='translate')
    parser.add_argument('source', type=argparse.FileType('r'))
    parser.add_argument('target', nargs='?',
                        type=argparse.FileType('w'), default=sys.stdout)
    parser.add_argument('--name', nargs='?', default='Main')
    parser.add_argument('--tree', '-t', action='count', default=0)
    return parser.parse_args()

def main():
    args = cli_parser()
    #read type table from file
    with open(types_file, 'r') as f:
        types = json.load(f)
    parser = lark.Lark(
        quack_grammar,
        parser='lalr'
    )
    
    #create initial parse tree
    tree = parser.parse(args.source.read())

    if args.tree == 1:
        print(tree.pretty())
        return

    #desugar binary operators
    transformer = Transformer()
    tree = transformer.transform(tree)

    if args.tree == 2:
        print(tree.pretty())
        return

    #decorate tree with types
    type_checker = TypeChecker(types)
    #keep track of whether any types were changed
    changed = True
    #decorate the tree until no node's types are changed
    while changed:
        changed = type_checker.visit(tree)

    #fill code array with assembly instructions
    code = []
    generator = Generator(code, types)
    generator.visit(tree)

    #output code to file or stdout
    generate_code(args.name, generator.variables, code, args.target)

if __name__ == '__main__' and not sys.flags.interactive:
    main()
