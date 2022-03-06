# Quack
A compiler for a Java-like object-oriented programming language.

## How to use

To compile and run a Quack program, run the following sequence of commands:
```
[qcc|quackc] <source_file> [name=Main]
bin/tiny_vm <name>
```
Or run the following single command:
```
quack <source_file> [name=Main]
```

The scripts default to creating a class named `Main`. This can be customized by providing a command-line argument. The class name is then passed to `bin/tiny_vm`.

## Files

The source code for the compiler is split into multiple files: `compile.py` is the entry point, and the `compiler/` folder contains Python files that implement the compiler.

## Test Cases

The `cases/` folder contains `correct.qk`, which contains a working Quack program that uses most Quack features, as well as various test programs that each have a compile error.

## Known Bugs

- The order in which classes are defined matters. If B extends A, A must be defined before B.
- Two classes cannot reference each other. If B references A, B must be defined after A, so A cannot reference B.
