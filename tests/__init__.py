"""NOOR test suite. Adds this folder to the import path so tests can `import helpers`
whether they are run with `discover -s tests` or one file at a time."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
