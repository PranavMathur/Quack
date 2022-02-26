#!/bin/bash

for name in "$@"
do
    python3 assemble.py "${name}.asm" "OBJ/${name}.json"
done
