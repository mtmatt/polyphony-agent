import ast
import os

def extract_symbols(file_path):
    try:
        with open(file_path, 'r') as f:
            tree = ast.parse(f.read())
        
        classes = []
        functions = []
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                classes.append(node.name)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                functions.append(node.name)
        return classes, functions
    except Exception as e:
        print(f"Error parsing {file_path}: {e}")
        return [], []

if __name__ == "__main__":
    c, f = extract_symbols("src/polyphony/utils.py")
    print(f"Classes: {c}")
    print(f"Functions: {f}")
