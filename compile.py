#!/usr/bin/python3

import lark
import argparse
import traceback
import json
import sys

from compiler.checker import FieldLoader, ReturnChecker, VarChecker
from compiler.errors import CompileError
from compiler.generator import Generator, generate_file
from compiler.loader import load_classes, create_main
from compiler.transformer import OpTransformer
from compiler.typechecker import TypeChecker, check_inherited

types_file = 'builtin_methods.json'
grammar_file = 'compiler/quack.lark'

#read an input and output file from the command line arguments
def cli_parser():
    parser = argparse.ArgumentParser(prog='qcc')
    parser.add_argument('source', type=argparse.FileType('r'))
    parser.add_argument('--name', nargs='?', default='Main')
    parser.add_argument('--tree', '-t', action='count', default=0)
    parser.add_argument('--verbose', '-v', action='store_true')
    parser.add_argument('--list', '-l', action='store_true')
    return parser.parse_args()

def main():
    args = cli_parser()
    #read type table from file
    with open(types_file, 'r') as f:
        types = json.load(f)

    with open(grammar_file, 'r') as f:
        quack_grammar = f.read()

    parser = lark.Lark(
        quack_grammar,
        parser='lalr',
        propagate_positions=True
    )

    try:
        #create initial parse tree
        tree = parser.parse(args.source.read())
    except lark.exceptions.LarkError as e:
        print(e, file=sys.stderr)
        exit(1)

    try:
        #if one tree option was given, output state of tree after parsing
        if args.tree == 1:
            print(tree.pretty())
            return

        #desugar binary operators
        op_transformer = OpTransformer()
        tree = op_transformer.transform(tree)

        #load user-defined classes and methods into method table
        load_classes(tree, types)

        #determine what fields each class has
        #and ensure that all fields are defined on all paths
        field_loader = FieldLoader(types)
        field_loader.visit(tree)

        #creates main class for execution
        create_main(tree, args.name)

        #ensure each method has a return statement on every path if necessary
        return_checker = ReturnChecker()
        return_checker.visit(tree)

        #if two tree options was given, output state of tree after transforming
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

        #ensure classes defined all fields inherited from supertypes
        #ensure overridden method signatures are compatible
        check_inherited(tree, types)

        #generate class objects and method code
        classes = []
        generator = Generator(classes, types)
        generator.visit(tree)

        #output code to files
        for class_ in classes:
            generate_file(class_)

        #output space separated list of classes
        #used by the compilation script
        if args.list:
            names = [i['name'] for i in classes]
            print(*names)
    except (CompileError, lark.exceptions.VisitError) as e:
        #convert lark error to original exception
        if isinstance(e, lark.exceptions.VisitError):
            e = e.orig_exc

        prefix = args.source.name
        #prefix error message with location, if given
        if e.meta is not None and not e.meta.empty:
            line = e.meta.line
            column = e.meta.column
            prefix += ' (%d:%d)' % (line, column)

        #output compile error message
        print('%s: %s' % (prefix, e), file=sys.stderr)
        #if verbose, print original exception and stack trace
        if args.verbose:
            traceback.print_exc()
        #exit with error code 1
        exit(1)

if __name__ == '__main__' and not sys.flags.interactive:
    main()
