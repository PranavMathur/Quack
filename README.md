# tiny_vm
A tiny virtual machine interpreter for Quack programs

## How to use

To compile and run a Quack program, run the following sequence of commands:
```
qcc <source_file> [name=Main]
./tiny_vm <name>
```

`qcc` defaults to creating a class named `Main`. This can be customized by providing a command-line argument to `qcc`. The class name is then passed to `tiny_vm`.

## Work in progress

This is intended to become the core of an interpreter for the Winter 2022
offering of CIS 461/561 compiler construction course at University of Oregon, 
if I can ready it in time. 

