#!/bin/bash -eu
compile_python_fuzzer fuzz/fuzz_parsers.py --add-data fuzz:fuzz --add-data codejig:codejig
