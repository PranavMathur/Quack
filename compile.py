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
    def neg(self, tree):
        children = [
            tree.children[0],
            'NEG',
            lark.Tree('m_args', [])
        ]
        return lark.Tree('m_call', children)

class Initializer(lark.visitors.Visitor_Recursive):
    def __default__(self, tree):
        tree.parent = None
        tree.type = ''
        for subtree in tree.children:
            if isinstance(subtree, lark.Tree):
                subtree.parent = tree

class TypeInferrer(lark.visitors.Visitor_Recursive):
    def __init__(self, types):
        self.variables = {}
        self.types = types
    def __default__(self, tree):
        literals = {
            'lit_number': 'Int',
            'lit_string': 'String',
            'lit_true': 'Boolean',
            'lit_false': 'Boolean',
            'lit_nothing': 'Nothing'
        }
        if tree.data in literals:
            tree.type = literals[tree.data]
        elif tree.data == 'var':
            name = str(tree.children[0])
            tree.type = self.variables.get(name, '')
        elif tree.data == 'assign':
            #tree.type = tree.children[2].type
            left = tree.children[0]
            tree.type = tree.children[1]
            if isinstance(left, lark.Token):
                self.variables[str(left)] = tree.type
        elif tree.data == 'm_call':
            left_type = tree.children[0].type
            m_name = tree.children[1]
            ret = self.types[left_type]['methods'][m_name]['ret']
            tree.type = ret

class Generator(lark.visitors.Visitor_Recursive):
    def __init__(self, code, types):
        super().__init__()
        self.code = code
        self.types = types
        self.variables = {}
    def lit_number(self, tree):
        self.code.append('const %s' % tree.children[0])
    def lit_true(self, tree):
        self.code.append('const true')
    def lit_false(self, tree):
        self.code.append('const false')
    def lit_nothing(self, tree):
        self.code.append('const nothing')
    def lit_string(self, tree):
        self.code.append('const %s' % tree.children[0])
    def var(self, tree):
        self.code.append('load %s' % tree.children[0])
    def assign(self, tree):
        name = tree.children[0]
        type = tree.children[1]
        self.variables[name] = type
        self.code.append('store %s' % name)
    def m_call(self, tree):
        left_type = tree.children[0].type
        self.code.append('call %s:%s' % (left_type, tree.children[1]))

def generate_code(name, variables, code, out):
    emit = lambda s: print(s, file=out)
    emit('.class %s:Obj\n\n.method $constructor' % name)
    if variables:
        emit('.local %s' % ','.join(i for i in variables))
    #emit('\tenter')
    for line in code:
        emit('\t' + line)
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

    initializer = Initializer()
    initializer.visit(tree)
    inferrer = TypeInferrer(types);
    inferrer.visit(tree)

    code = []
    generator = Generator(code, types)
    generator.visit(tree)

    generate_code(args.name, generator.variables, code, args.target)

if __name__ == '__main__' and not sys.flags.interactive:
    main()
