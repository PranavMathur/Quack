# Quack
A compiler for a Java-like object-oriented programming language.

## How to use

To compile and run a Quack program, run the following sequence of commands:
```
[qcc|quackc] <source_file> [name=Main]
./tiny_vm <name>
```
Or run the following single command:
```
quack <source_file> [name=Main]
```

The scripts default to creating a class named `Main`. This can be customized by providing a command-line argument. The class name is then passed to `tiny_vm`.

## Files

The source code for the compiler is split into fives files: `compile.py` is the entry point, and the `compiler/` folder contains `grammar.py`, `transformer.py`, `typechecker.py`, and `generator.py`.
