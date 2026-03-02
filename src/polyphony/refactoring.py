"""
Cross-file refactoring support using AST analysis.

Provides safe multi-file rename operations and automated import updates.
"""

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class SymbolUsage:
    """Represents a usage of a symbol in a file."""

    name: str
    file_path: Path
    line: int
    column: int
    usage_type: str  # 'import', 'definition', 'reference', 'attribute'
    context: str = ""  # Surrounding context for verification


@dataclass
class RenameOperation:
    """Represents a rename operation to be performed."""

    old_name: str
    new_name: str
    symbol_type: str  # 'function', 'class', 'variable', 'module'
    affected_files: list[Path] = field(default_factory=list)
    usages: list[SymbolUsage] = field(default_factory=list)


@dataclass
class ImportUpdate:
    """Represents an import statement that needs updating."""

    file_path: Path
    old_import: str
    new_import: str
    line_number: int
    is_from_import: bool


class ASTAnalyzer(ast.NodeVisitor):
    """AST visitor that collects symbol definitions and usages."""

    def __init__(self, file_path: Path):
        self.file_path = file_path
        self.symbols: dict[str, list[SymbolUsage]] = {}
        self.imports: list[SymbolUsage] = []
        self.current_scope: list[str] = []

    def add_usage(self, name: str, line: int, column: int, usage_type: str):
        """Record a symbol usage."""
        usage = SymbolUsage(
            name=name,
            file_path=self.file_path,
            line=line,
            column=column,
            usage_type=usage_type,
        )
        if name not in self.symbols:
            self.symbols[name] = []
        self.symbols[name].append(usage)

    def visit_Import(self, node):
        """Visit import statements."""
        for alias in node.names:
            self.add_usage(
                alias.name,
                node.lineno,
                node.col_offset,
                "import",
            )
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        """Visit from ... import statements."""
        module = node.module or ""
        for alias in node.names:
            name = alias.asname or alias.name
            self.add_usage(
                name,
                node.lineno,
                node.col_offset + 5,  # After 'from '
                f"import_from:{module}",
            )
        self.generic_visit(node)

    def visit_FunctionDef(self, node):
        """Visit function definitions."""
        self.add_usage(
            node.name,
            node.lineno,
            node.col_offset + 4,  # After 'def '
            "definition:function",
        )
        self.current_scope.append(node.name)
        self.generic_visit(node)
        self.current_scope.pop()

    def visit_AsyncFunctionDef(self, node):
        """Visit async function definitions."""
        self.add_usage(
            node.name,
            node.lineno,
            node.col_offset + 9,  # After 'async def '
            "definition:function",
        )
        self.current_scope.append(node.name)
        self.generic_visit(node)
        self.current_scope.pop()

    def visit_ClassDef(self, node):
        """Visit class definitions."""
        self.add_usage(
            node.name,
            node.lineno,
            node.col_offset + 6,  # After 'class '
            "definition:class",
        )
        self.current_scope.append(node.name)
        self.generic_visit(node)
        self.current_scope.pop()

    def visit_Name(self, node):
        """Visit name references."""
        if isinstance(node.ctx, ast.Store):
            ctx_type = "definition:variable"
        else:
            ctx_type = "reference"
        self.add_usage(
            node.id,
            node.lineno,
            node.col_offset,
            ctx_type,
        )
        self.generic_visit(node)

    def visit_Attribute(self, node):
        """Visit attribute access (e.g., obj.attr)."""
        if isinstance(node.ctx, ast.Store):
            self.add_usage(
                node.attr,
                node.lineno,
                node.col_offset,
                "definition:attribute",
            )
        else:
            self.add_usage(
                node.attr,
                node.lineno,
                node.col_offset,
                "attribute",
            )
        self.generic_visit(node)


class RefactoringEngine:
    """Engine for performing cross-file refactorings."""

    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.file_cache: dict[Path, str] = {}
        self.ast_cache: dict[Path, ASTAnalyzer] = {}

    def analyze_file(self, file_path: Path) -> ASTAnalyzer:
        """Analyze a single file and return the AST analyzer."""
        if file_path in self.ast_cache:
            return self.ast_cache[file_path]

        try:
            content = file_path.read_text(encoding="utf-8")
            self.file_cache[file_path] = content

            tree = ast.parse(content)
            analyzer = ASTAnalyzer(file_path)
            analyzer.visit(tree)

            self.ast_cache[file_path] = analyzer
            return analyzer
        except SyntaxError as e:
            raise ValueError(f"Syntax error in {file_path}: {e}")
        except Exception as e:
            raise ValueError(f"Failed to analyze {file_path}: {e}")

    def analyze_project(self) -> dict[Path, ASTAnalyzer]:
        """Analyze all Python files in the project."""
        python_files = list(self.project_root.rglob("*.py"))
        results = {}

        for file_path in python_files:
            if "__pycache__" in str(file_path):
                continue
            try:
                analyzer = self.analyze_file(file_path)
                results[file_path] = analyzer
            except ValueError:
                continue  # Skip files with syntax errors

        return results

    def find_symbol_usages(
        self, symbol_name: str, symbol_type: str | None = None
    ) -> list[SymbolUsage]:
        """Find all usages of a symbol across the project."""
        usages = []
        analysis = self.analyze_project()

        for analyzer in analysis.values():
            if symbol_name in analyzer.symbols:
                for usage in analyzer.symbols[symbol_name]:
                    if symbol_type is None or usage.usage_type.startswith(symbol_type):
                        usages.append(usage)

        return usages

    def plan_rename(
        self, old_name: str, new_name: str, symbol_type: str = "function"
    ) -> RenameOperation:
        """Plan a rename operation across all files."""
        usages = self.find_symbol_usages(old_name, symbol_type.split(":")[0])

        affected_files = list({usage.file_path for usage in usages})

        return RenameOperation(
            old_name=old_name,
            new_name=new_name,
            symbol_type=symbol_type,
            affected_files=affected_files,
            usages=usages,
        )

    def _is_word_boundary(self, text: str, pos: int, name: str) -> bool:
        """Check if position represents a word boundary for safe replacement."""
        # Check before
        if pos > 0 and text[pos - 1].isalnum():
            return False
        # Check after
        end_pos = pos + len(name)
        if end_pos < len(text) and text[end_pos].isalnum():
            return False
        return True

    def execute_rename(self, operation: RenameOperation) -> dict[Path, str]:
        """Execute a rename operation and return modified files."""
        modified_files = {}

        for file_path in operation.affected_files:
            if file_path not in self.file_cache:
                self.file_cache[file_path] = file_path.read_text(encoding="utf-8")

            content = self.file_cache[file_path]
            original_content = content
            new_content = content

            # Get usages in this file, sorted by position (reverse to avoid offset issues)
            file_usages = [u for u in operation.usages if u.file_path == file_path]
            file_usages.sort(key=lambda u: (u.line, u.column), reverse=True)

            # Convert to lines for precise replacement
            lines = new_content.split("\n")

            for usage in file_usages:
                if usage.line <= 0 or usage.line > len(lines):
                    continue

                line_idx = usage.line - 1
                line = lines[line_idx]

                # Check if old_name appears at expected position
                pos = usage.column
                if pos < len(line) and line[pos:pos + len(operation.old_name)] == operation.old_name:
                    # Verify word boundaries
                    if self._is_word_boundary(line, pos, operation.old_name):
                        lines[line_idx] = line[:pos] + operation.new_name + line[pos + len(operation.old_name):]

            new_content = "\n".join(lines)

            if new_content != original_content:
                self.file_cache[file_path] = new_content
                modified_files[file_path] = new_content

        return modified_files

    def save_changes(self, files: dict[Path, str]) -> None:
        """Save modified files to disk."""
        for file_path, content in files.items():
            file_path.write_text(content, encoding="utf-8")
            # Update caches
            self.file_cache[file_path] = content
            if file_path in self.ast_cache:
                del self.ast_cache[file_path]  # Invalidate AST cache

    def extract_function(
        self,
        source_file: Path,
        function_name: str,
        target_file: Path | None = None,
        new_module_name: str | None = None,
    ) -> dict[Path, str]:
        """
        Extract a function to a new file and update imports.

        Returns a dict of modified files with their new contents.
        """
        if source_file not in self.file_cache:
            self.file_cache[source_file] = source_file.read_text(encoding="utf-8")

        content = self.file_cache[source_file]
        tree = ast.parse(content)

        # Find the function
        function_node = None
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function_name:
                function_node = node
                break

        if function_node is None:
            raise ValueError(f"Function '{function_name}' not found in {source_file}")

        # Extract function source
        lines = content.split("\n")
        start_line = function_node.lineno - 1
        end_line = function_node.end_lineno or start_line + 1
        function_source = "\n".join(lines[start_line:end_line])

        modifications = {}

        # Create target file if specified
        if target_file and new_module_name:
            target_file.parent.mkdir(parents=True, exist_ok=True)
            target_content = f"\"\"\"Extracted from {source_file.name}.\"\"\"\n\n{function_source}\n"
            modifications[target_file] = target_content

            # Update source file: remove function and add import
            new_source_lines = lines[:start_line] + lines[end_line:]
            import_line = f"from {new_module_name} import {function_name}\n"

            # Find best place to add import
            import_idx = 0
            for i, line in enumerate(new_source_lines):
                if line.startswith("import ") or line.startswith("from "):
                    import_idx = i + 1

            new_source_lines.insert(import_idx, import_line)
            modified_source = "\n".join(new_source_lines)
            modifications[source_file] = modified_source

        return modifications

    def rename_symbol(
        self,
        old_name: str,
        new_name: str,
        symbol_type: str = "function",
        preview: bool = False,
    ) -> dict[Path, str]:
        """
        Rename a symbol across all files.

        Args:
            preview: If True, don't save changes, just return what would change

        Returns:
            Dictionary of modified files and their new contents
        """
        operation = self.plan_rename(old_name, new_name, symbol_type)

        if not operation.usages:
            return {}

        modified = self.execute_rename(operation)

        if not preview and modified:
            self.save_changes(modified)

        return modified

    def get_rename_preview(
        self, old_name: str, new_name: str, symbol_type: str = "function"
    ) -> list[dict[str, Any]]:
        """Get a preview of what would be changed in a rename operation."""
        operation = self.plan_rename(old_name, new_name, symbol_type)

        preview = []
        for usage in operation.usages:
            preview.append({
                "file": str(usage.file_path.relative_to(self.project_root)),
                "line": usage.line,
                "column": usage.column,
                "type": usage.usage_type,
                "name": old_name,
                "new_name": new_name,
            })

        return preview
