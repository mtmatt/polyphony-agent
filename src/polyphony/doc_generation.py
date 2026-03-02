"""
Documentation Generation Module

Auto-generates API docs, user guides, and Mermaid architecture diagrams from the codebase.
"""

import ast
import inspect
import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel


class APIDocEntry(BaseModel):
    """Represents a single API documentation entry."""
    name: str
    docstring: str | None
    signature: str
    module: str
    kind: str  # function, class, method
    line_number: int


class ClassDiagramEntry(BaseModel):
    """Represents a class for diagram generation."""
    name: str
    module: str
    methods: list[str]
    attributes: list[str]
    base_classes: list[str]


class ModuleInfo(BaseModel):
    """Represents module information for documentation."""
    name: str
    path: str
    docstring: str | None
    functions: list[APIDocEntry]
    classes: list[ClassDiagramEntry]


def parse_module(file_path: Path) -> ModuleInfo | None:
    """Parse a Python module and extract API documentation."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            tree = ast.parse(f.read())
    except (SyntaxError, IOError):
        return None
    
    module_name = file_path.stem
    docstring = ast.get_docstring(tree)
    
    functions: list[APIDocEntry] = []
    classes: list[ClassDiagramEntry] = []
    
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            func_doc = APIDocEntry(
                name=node.name,
                docstring=ast.get_docstring(node),
                signature=get_function_signature(node),
                module=module_name,
                kind="function",
                line_number=node.lineno
            )
            functions.append(func_doc)
        
        elif isinstance(node, ast.ClassDef):
            methods = []
            attributes = []
            base_classes = [base.id if isinstance(base, ast.Name) else str(base) for base in node.bases]
            
            for item in node.body:
                if isinstance(item, ast.FunctionDef):
                    methods.append(item.name)
                elif isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                    attributes.append(item.target.id)
            
            class_info = ClassDiagramEntry(
                name=node.name,
                module=module_name,
                methods=methods,
                attributes=attributes,
                base_classes=base_classes
            )
            classes.append(class_info)
    
    return ModuleInfo(
        name=module_name,
        path=str(file_path),
        docstring=docstring,
        functions=functions,
        classes=classes
    )


def get_function_signature(node: ast.FunctionDef) -> str:
    """Extract function signature from AST node."""
    args = []
    
    # Handle args
    for arg in node.args.args:
        arg_str = arg.arg
        if arg.annotation:
            if isinstance(arg.annotation, ast.Name):
                arg_str += f": {arg.annotation.id}"
            elif isinstance(arg.annotation, ast.Constant):
                arg_str += f": {arg.annotation.value}"
        args.append(arg_str)
    
    # Handle defaults
    defaults_start = len(args) - len(node.args.defaults)
    for i, default in enumerate(node.args.defaults):
        if isinstance(default, ast.Constant):
            args[defaults_start + i] += f"={default.value!r}"
        elif isinstance(default, ast.Name):
            args[defaults_start + i] += f"={default.id}"
    
    sig = f"({', '.join(args)})"
    
    # Handle return annotation
    if node.returns:
        if isinstance(node.returns, ast.Name):
            sig += f" -> {node.returns.id}"
        elif hasattr(node.returns, 'value'):
            sig += f" -> {node.returns.value}"
    
    return sig


def generate_api_docs(source_path: Path, output_path: Path) -> None:
    """Generate API documentation markdown from source code."""
    modules: list[ModuleInfo] = []
    
    # Walk through source directory
    for py_file in source_path.rglob('*.py'):
        if py_file.name.startswith('test_'):
            continue
        module_info = parse_module(py_file)
        if module_info:
            modules.append(module_info)
    
    # Generate markdown
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write("# API Documentation\n\n")
        f.write("Auto-generated API documentation.\n\n")
        
        for module in modules:
            f.write(f"## Module: `{module.name}`\n\n")
            if module.docstring:
                f.write(f"{module.docstring}\n\n")
            
            if module.functions:
                f.write("### Functions\n\n")
                for func in module.functions:
                    f.write(f"#### `{func.name}{func.signature}`\n\n")
                    if func.docstring:
                        f.write(f"{func.docstring}\n\n")
            
            if module.classes:
                f.write("### Classes\n\n")
                for cls in module.classes:
                    bases = f"({', '.join(cls.base_classes)})" if cls.base_classes else ""
                    f.write(f"#### `{cls.name}{bases}`\n\n")
                    if cls.attributes:
                        f.write("**Attributes:**\n")
                        for attr in cls.attributes:
                            f.write(f"- `{attr}`\n")
                        f.write("\n")
                    if cls.methods:
                        f.write("**Methods:**\n")
                        for method in cls.methods:
                            f.write(f"- `{method}()`\n")
                        f.write("\n")


def generate_user_guide(source_path: Path, output_path: Path) -> None:
    """Generate user guide markdown from analyzed codebase."""
    modules: list[ModuleInfo] = []
    
    for py_file in source_path.rglob('*.py'):
        if py_file.name.startswith('test_'):
            continue
        module_info = parse_module(py_file)
        if module_info:
            modules.append(module_info)
    
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write("# User Guide\n\n")
        f.write("Welcome to the user guide for this project.\n\n")
        f.write("## Getting Started\n\n")
        f.write("This guide will help you understand the main components and how to use them.\n\n")
        
        f.write("## Module Overview\n\n")
        for module in modules:
            f.write(f"### {module.name}\n")
            if module.docstring:
                first_line = module.docstring.split('\n')[0]
                f.write(f"{first_line}\n")
            
            if module.classes:
                f.write(f"**Key Classes:** {', '.join(cls.name for cls in module.classes)}\n")
            f.write("\n")
        
        f.write("## Usage Examples\n\n")
        f.write("```python\n")
        f.write("# Import the main components\n")
        for module in modules[:3]:  # Top 3 modules as examples
            if module.classes:
                f.write(f"from {module.name} import {module.classes[0].name}\n")
        f.write("\n")
        f.write("# Initialize and use\n")
        for module in modules[:1]:
            if module.classes:
                f.write(f"{module.classes[0].name.lower()} = {module.classes[0].name}()\n")
        f.write("```\n")


def generate_class_diagram(modules: list[ModuleInfo]) -> str:
    """Generate a Mermaid class diagram from module information."""
    lines = ["classDiagram"]
    relationships: set[str] = set()
    
    for module in modules:
        for cls in module.classes:
            lines.append(f"    class {cls.name}")
            
            for attr in cls.attributes:
                lines.append(f"    {cls.name} : +{attr}")
            
            for method in cls.methods:
                lines.append(f"    {cls.name} : +{method}()")
            
            for base in cls.base_classes:
                if base not in ('BaseModel', 'ABC', 'Enum', 'object'):
                    relationships.add(f"    {base} <|-- {cls.name}")
    
    lines.extend(sorted(relationships))
    return '\n'.join(lines)


def generate_component_diagram(modules: list[ModuleInfo]) -> str:
    """Generate a Mermaid component diagram showing module dependencies."""
    lines = ["graph TB"]
    
    module_names = [m.name for m in modules]
    
    for module in modules:
        lines.append(f"    subgraph {module.name}")
        for cls in module.classes[:5]:  # Limit to 5 classes per module
            lines.append(f"        {module.name}_{cls.name}[{cls.name}]")
        lines.append("    end")
    
    return '\n'.join(lines)


def generate_architecture_diagrams(source_path: Path, output_path: Path) -> None:
    """Generate Mermaid architecture diagrams."""
    modules: list[ModuleInfo] = []
    
    for py_file in source_path.rglob('*.py'):
        if py_file.name.startswith('test_'):
            continue
        module_info = parse_module(py_file)
        if module_info:
            modules.append(module_info)
    
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write("# Architecture Diagrams\n\n")
        f.write("Visual representations of the system architecture.\n\n")
        
        # Class Diagram
        f.write("## Class Diagram\n\n")
        f.write("```mermaid\n")
        f.write(generate_class_diagram(modules))
        f.write("\n```\n\n")
        
        # Component Diagram
        f.write("## Component Diagram\n\n")
        f.write("```mermaid\n")
        f.write(generate_component_diagram(modules))
        f.write("\n```\n\n")
        
        # Module Statistics
        f.write("## Module Statistics\n\n")
        f.write("| Module | Classes | Functions |\n")
        f.write("|--------|---------|-----------|\n")
        for module in modules:
            f.write(f"| {module.name} | {len(module.classes)} | {len(module.functions)} |\n")


def generate_all_docs(source_dir: str | Path, output_dir: str | Path) -> dict[str, Path]:
    """
    Generate all documentation types.
    
    Args:
        source_dir: The source code directory
        output_dir: Where to write the documentation
    
    Returns:
        Dictionary mapping doc type to file path
    """
    source_path = Path(source_dir)
    output_path = Path(output_dir)
    
    output_path.mkdir(parents=True, exist_ok=True)
    
    results: dict[str, Path] = {}
    
    api_path = output_path / "api_docs.md"
    generate_api_docs(source_path, api_path)
    results["api"] = api_path
    
    guide_path = output_path / "user_guide.md"
    generate_user_guide(source_path, guide_path)
    results["guide"] = guide_path
    
    arch_path = output_path / "architecture.md"
    generate_architecture_diagrams(source_path, arch_path)
    results["architecture"] = arch_path
    
    return results


def extract_function_code(func: Any) -> str | None:
    """Extract source code of a function for documentation."""
    try:
        return inspect.getsource(func)
    except (TypeError, IOError):
        return None


def generate_markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    """Generate a markdown table from headers and rows."""
    lines = []
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("|" + "|".join("---" for _ in headers) + "|")
    for row in rows:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def format_docstring(docstring: str | None, indent: str = "") -> str:
    """Format a docstring for markdown output."""
    if not docstring:
        return ""
    lines = docstring.split("\n")
    return "\n".join(indent + line for line in lines)
