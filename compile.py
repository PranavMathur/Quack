#!/usr/bin/python3

import lark
import argparse
import traceback
import json
import sys

from compiler.errors import CompileError
from compiler.grammar import quack_grammar
from compiler.generator import Generator, generate_code
from compiler.transformer import Transformer
from compiler.typechecker import TypeChecker
from compiler.varchecker import VarChecker

types_file = 'builtin_methods.json'

#read an input and output file from the command line arguments
def cli_parser():
    parser = argparse.ArgumentParser(prog='translate')
    parser.add_argument('source', type=argparse.FileType('r'))
    parser.add_argument('target', nargs='?',
                        type=argparse.FileType('w'), default=sys.stdout)
    parser.add_argument('--name', nargs='?', default='Main')
    parser.add_argument('--tree', '-t', action='count', default=0)
    parser.add_argument('--verbose', '-v', action='store_true')
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
    
    try:
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

        #check that all variables are defined before use
        #variables must be defined in all possible execution paths before use
        var_checker = VarChecker()
        var_checker.visit(tree)

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
    except CompileError as e:
        print('Error: ' + str(e), file=sys.stderr)
        if args.verbose:
            traceback.print_exc()
        exit(1)

if __name__ == '__main__' and not sys.flags.interactive:
    main()
