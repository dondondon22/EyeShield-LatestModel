#!/usr/bin/env python
import ast
import sys

files = [
    r'c:\Users\Computer\Desktop\EyeShield\Frontend\testSample\model_inference.py',
    r'c:\Users\Computer\Desktop\EyeShield\Frontend\testSample\main.py'
]

for filepath in files:
    try:
        with open(filepath, 'r') as f:
            ast.parse(f.read())
        print(f'{filepath.split(chr(92))[-1]}: OK')
    except Exception as e:
        print(f'{filepath.split(chr(92))[-1]}: ERROR - {e}')
        sys.exit(1)
