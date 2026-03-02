import ast
import re
import os
from typing import List, Optional

def get_python_symbols(file_path: str) -> List[str]:
    """Extracts symbols from a Python file using AST."""
    symbols = []
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            tree = ast.parse(content)
            
            for node in tree.body:
                if isinstance(node, ast.ClassDef):
                    bases = ""
                    if node.bases:
                        base_names = []
                        for base in node.bases:
                            if isinstance(base, ast.Name):
                                base_names.append(base.id)
                            elif isinstance(base, ast.Attribute):
                                base_names.append(f"{getattr(base.value, 'id', '')}.{base.attr}")
                        if base_names:
                            bases = f"({', '.join(base_names)})"
                    
                    symbols.append(f"Class {node.name}{bases}")
                    
                    # Docstring
                    doc = ast.get_docstring(node)
                    if doc:
                        first_line = doc.strip().split('\n')[0]
                        symbols.append(f"    \"\"\"{first_line}\"\"\"")

                    # Methods
                    for subnode in node.body:
                        if isinstance(subnode, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            if subnode.name.startswith('_') and not (subnode.name.startswith('__') and subnode.name.endswith('__')):
                                continue
                            
                            args = [arg.arg for arg in subnode.args.args]
                            sig = f"{subnode.name}({', '.join(args)})"
                            symbols.append(f"    Method {sig}")
                            
                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if node.name.startswith('_'):
                        continue
                        
                    args = [arg.arg for arg in node.args.args]
                    sig = f"{node.name}({', '.join(args)})"
                    symbols.append(f"Function {sig}")
                    
                    doc = ast.get_docstring(node)
                    if doc:
                        first_line = doc.strip().split('\n')[0]
                        symbols.append(f"    \"\"\"{first_line}\"\"\"")
    except Exception:
        pass
    return symbols

def get_js_ts_symbols(file_path: str) -> List[str]:
    """Extracts symbols from a JS/TS file using regex."""
    symbols = []
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
            # Classes
            for match in re.finditer(r"(?:export\s+)?class\s+(\w+)(?:\s+extends\s+\w+)?", content):
                symbols.append(f"Class {match.group(1)}")
            
            # Functions
            for match in re.finditer(r"(?:export\s+)?function\s+(\w+)\s*\((.*?)\)", content):
                symbols.append(f"Function {match.group(1)}({match.group(2)})")
            
            # Arrow functions (named)
            for match in re.finditer(r"(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*\((.*?)\)\s*=>", content):
                symbols.append(f"ArrowFunction {match.group(1)}({match.group(2)})")
            
            # Interfaces (TS)
            for match in re.finditer(r"(?:export\s+)?interface\s+(\w+)", content):
                symbols.append(f"Interface {match.group(1)}")
            
            # Types (TS)
            for match in re.finditer(r"(?:export\s+)?type\s+(\w+)", content):
                symbols.append(f"Type {match.group(1)}")
                
    except Exception:
        pass
    return symbols

def get_go_symbols(file_path: str) -> List[str]:
    """Extracts symbols from a Go file using regex."""
    symbols = []
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
            # Structs
            for match in re.finditer(r"type\s+(\w+)\s+struct", content):
                symbols.append(f"Struct {match.group(1)}")
            
            # Interfaces
            for match in re.finditer(r"type\s+(\w+)\s+interface", content):
                symbols.append(f"Interface {match.group(1)}")
            
            # Functions (regular)
            for match in re.finditer(r"func\s+(\w+)\s*\((.*?)\)", content):
                symbols.append(f"Function {match.group(1)}({match.group(2)})")
            
            # Methods
            for match in re.finditer(r"func\s+\((.*?)\)\s+(\w+)\s*\((.*?)\)", content):
                symbols.append(f"Method ({match.group(1)}) {match.group(2)}({match.group(3)})")
                
    except Exception:
        pass
    return symbols

def get_rust_symbols(file_path: str) -> List[str]:
    """Extracts symbols from a Rust file using regex."""
    symbols = []
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
            # Structs
            for match in re.finditer(r"(?:pub\s+)?struct\s+(\w+)", content):
                symbols.append(f"Struct {match.group(1)}")
            
            # Enums
            for match in re.finditer(r"(?:pub\s+)?enum\s+(\w+)", content):
                symbols.append(f"Enum {match.group(1)}")
            
            # Traits
            for match in re.finditer(r"(?:pub\s+)?trait\s+(\w+)", content):
                symbols.append(f"Trait {match.group(1)}")
            
            # Impls
            for match in re.finditer(r"impl\s+(?:.*for\s+)?(\w+)", content):
                symbols.append(f"Impl {match.group(1)}")
            
            # Functions
            for match in re.finditer(r"(?:pub\s+)?fn\s+(\w+)\s*\((.*?)\)", content):
                symbols.append(f"Function {match.group(1)}({match.group(2)})")
                
    except Exception:
        pass
    return symbols

def get_java_symbols(file_path: str) -> List[str]:
    """Extracts symbols from a Java file using regex."""
    symbols = []
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
            # Classes
            for match in re.finditer(r"(?:public|private|protected|static|\s)*class\s+(\w+)", content):
                symbols.append(f"Class {match.group(1)}")
            
            # Interfaces
            for match in re.finditer(r"(?:public|private|protected|static|\s)*interface\s+(\w+)", content):
                symbols.append(f"Interface {match.group(1)}")
            
            # Enums
            for match in re.finditer(r"(?:public|private|protected|static|\s)*enum\s+(\w+)", content):
                symbols.append(f"Enum {match.group(1)}")
            
            # Methods - rough regex for Java methods
            # Matches: [modifiers] [Type] name([args]) { or ;
            # This is tricky because of return types and modifiers.
            # Simplified: (public|private|protected|static)\s+[\w<>, \[\]]+\s+(\w+)\s*\((.*?)\)
            for match in re.finditer(r"(?:public|private|protected|static)\s+[\w<>, \[\]]+\s+(\w+)\s*\((.*?)\)", content):
                if match.group(1) not in ("class", "interface", "enum", "return", "new"):
                    symbols.append(f"Method {match.group(1)}({match.group(2)})")
                
    except Exception:
        pass
    return symbols

def get_file_symbols(file_path: str) -> List[str]:
    """Dispatches to the correct symbol extractor based on file extension."""
    ext = os.path.splitext(file_path)[1].lower()
    if ext == '.py':
        return get_python_symbols(file_path)
    elif ext in ('.js', '.ts', '.jsx', '.tsx'):
        return get_js_ts_symbols(file_path)
    elif ext == '.go':
        return get_go_symbols(file_path)
    elif ext == '.rs':
        return get_rust_symbols(file_path)
    elif ext == '.java':
        return get_java_symbols(file_path)
    return []
