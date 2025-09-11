#!/usr/bin/env python3
"""
Reliability pattern checker for pre-commit hooks.
Enforces coding patterns that improve reliability and robustness.
"""
import ast
import sys
import os
from pathlib import Path
from typing import List, Tuple, Set
import re

class ReliabilityPatternChecker(ast.NodeVisitor):
    """AST visitor to check for reliability patterns."""
    
    def __init__(self, filename: str):
        self.filename = filename
        self.issues: List[Tuple[int, str]] = []
        self.has_timeout_imports = False
        self.has_logging_imports = False
        self.function_names: Set[str] = set()
        self.class_names: Set[str] = set()
        
    def visit_Import(self, node):
        """Check imports for reliability-related modules."""
        for alias in node.names:
            if alias.name in ['time', 'timeout', 'signal']:
                self.has_timeout_imports = True
            elif alias.name in ['logging']:
                self.has_logging_imports = True
        self.generic_visit(node)
    
    def visit_ImportFrom(self, node):
        """Check from imports."""
        if node.module in ['contextlib', 'typing', 'logging']:
            if node.module == 'logging':
                self.has_logging_imports = True
            elif node.module == 'contextlib' and any(alias.name == 'contextmanager' for alias in node.names):
                pass  # Good pattern
        self.generic_visit(node)
    
    def visit_FunctionDef(self, node):
        """Check function definitions for reliability patterns."""
        self.function_names.add(node.name)
        
        # Check for external I/O functions without error handling
        if any(keyword in node.name.lower() for keyword in ['download', 'upload', 'request', 'fetch', 'send']):
            if not self._has_try_except_in_function(node):
                self.issues.append((node.lineno, f"Function '{node.name}' performs I/O but lacks error handling"))
        
        # Check for functions that should have timeouts
        if any(keyword in node.name.lower() for keyword in ['process', 'render', 'extract', 'convert']):
            if not self._function_has_timeout_context(node):
                self.issues.append((node.lineno, f"Long-running function '{node.name}' should implement timeout protection"))
        
        # Check for input validation in public functions
        if not node.name.startswith('_') and node.args.args:
            if not self._has_input_validation(node):
                self.issues.append((node.lineno, f"Public function '{node.name}' should validate inputs"))
        
        self.generic_visit(node)
    
    def visit_ClassDef(self, node):
        """Check class definitions."""
        self.class_names.add(node.name)
        
        # Check for service/client classes
        if any(suffix in node.name for suffix in ['Service', 'Client', 'Manager']):
            if not self._class_has_error_handling_methods(node):
                self.issues.append((node.lineno, f"Service class '{node.name}' should have comprehensive error handling"))
        
        self.generic_visit(node)
    
    def visit_With(self, node):
        """Check context manager usage."""
        # Good pattern - context managers for resource management
        self.generic_visit(node)
    
    def visit_Try(self, node):
        """Check try-except blocks."""
        # Check for bare except clauses
        for handler in node.handlers:
            if handler.type is None:
                self.issues.append((handler.lineno, "Avoid bare 'except:' clauses - catch specific exceptions"))
            elif isinstance(handler.type, ast.Name) and handler.type.id == 'Exception':
                # Check if it re-raises or logs
                if not self._handler_logs_or_reraises(handler):
                    self.issues.append((handler.lineno, "Catching 'Exception' should log error or re-raise"))
        
        self.generic_visit(node)
    
    def visit_Call(self, node):
        """Check function calls for reliability patterns."""
        # Check for time.sleep calls (potential flakiness)
        if (isinstance(node.func, ast.Attribute) and 
            isinstance(node.func.value, ast.Name) and 
            node.func.value.id == 'time' and 
            node.func.attr == 'sleep'):
            self.issues.append((node.lineno, "Avoid time.sleep in tests - use mocking or deterministic timing"))
        
        # Check for unguarded external calls
        if (isinstance(node.func, ast.Attribute) and 
            node.func.attr in ['get', 'post', 'put', 'delete', 'head']):
            # This is likely an HTTP call - should have timeout
            if not self._call_has_timeout_arg(node):
                self.issues.append((node.lineno, f"HTTP call should specify timeout parameter"))
        
        self.generic_visit(node)
    
    def _has_try_except_in_function(self, func_node) -> bool:
        """Check if function has try-except blocks."""
        for node in ast.walk(func_node):
            if isinstance(node, ast.Try):
                return True
        return False
    
    def _function_has_timeout_context(self, func_node) -> bool:
        """Check if function uses timeout context or has timeout parameter."""
        # Check for timeout parameter
        for arg in func_node.args.args:
            if 'timeout' in arg.arg.lower():
                return True
        
        # Check for timeout context manager usage
        for node in ast.walk(func_node):
            if (isinstance(node, ast.With) and 
                any(isinstance(item.context_expr, ast.Call) and 
                    getattr(item.context_expr.func, 'id', '').endswith('timeout') 
                    for item in node.items)):
                return True
        
        return False
    
    def _has_input_validation(self, func_node) -> bool:
        """Check if function has input validation."""
        # Look for validation patterns in first few statements
        for i, stmt in enumerate(func_node.body[:5]):  # Check first 5 statements
            if isinstance(stmt, ast.If):
                # Check for validation patterns
                if self._is_validation_condition(stmt.test):
                    return True
            elif isinstance(stmt, ast.Raise):
                return True  # Immediate raise (validation)
        return False
    
    def _is_validation_condition(self, node) -> bool:
        """Check if condition looks like input validation."""
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            return True
        if isinstance(node, ast.Compare):
            # Look for None checks, empty checks, etc.
            for comparator in node.comparators:
                if (isinstance(comparator, ast.Constant) and comparator.value is None) or \
                   (isinstance(comparator, ast.Constant) and comparator.value == ''):
                    return True
        return False
    
    def _class_has_error_handling_methods(self, class_node) -> bool:
        """Check if class has error handling methods."""
        method_names = []
        for node in class_node.body:
            if isinstance(node, ast.FunctionDef):
                method_names.append(node.name)
        
        # Look for error handling patterns
        error_patterns = ['_handle_error', '_log_error', 'handle_exception', 'error_handler']
        return any(pattern in ' '.join(method_names) for pattern in error_patterns)
    
    def _handler_logs_or_reraises(self, handler) -> bool:
        """Check if exception handler logs or re-raises."""
        for stmt in handler.body:
            if isinstance(stmt, ast.Raise):
                return True
            elif (isinstance(stmt, ast.Call) and 
                  isinstance(stmt.func, ast.Attribute) and 
                  stmt.func.attr in ['error', 'warning', 'exception']):
                return True
        return False
    
    def _call_has_timeout_arg(self, call_node) -> bool:
        """Check if function call has timeout argument."""
        # Check keyword arguments
        for keyword in call_node.keywords:
            if keyword.arg and 'timeout' in keyword.arg.lower():
                return True
        return False

def check_file_patterns(filepath: Path) -> List[Tuple[int, str]]:
    """Check a Python file for reliability patterns."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Parse AST
        tree = ast.parse(content, filename=str(filepath))
        
        # Run checker
        checker = ReliabilityPatternChecker(str(filepath))
        checker.visit(tree)
        
        # Additional regex-based checks
        additional_issues = check_regex_patterns(content, str(filepath))
        
        return checker.issues + additional_issues
        
    except SyntaxError as e:
        return [(e.lineno or 0, f"Syntax error: {e.msg}")]
    except Exception as e:
        return [(0, f"Error analyzing file: {e}")]

def check_regex_patterns(content: str, filename: str) -> List[Tuple[int, str]]:
    """Check for patterns using regex."""
    issues = []
    lines = content.split('\n')
    
    for i, line in enumerate(lines, 1):
        # Check for hardcoded timeouts (should be configurable)
        if re.search(r'time\.sleep\(\s*\d+\s*\)', line):
            issues.append((i, "Hardcoded sleep duration - consider making configurable"))
        
        # Check for print statements (should use logging)
        if re.search(r'\bprint\s*\(', line) and 'test' not in filename.lower():
            issues.append((i, "Use logging instead of print statements"))
        
        # Check for TODO/FIXME without issue links
        todo_match = re.search(r'#\s*(TODO|FIXME|XXX)', line, re.IGNORECASE)
        if todo_match and not re.search(r'#\d+', line):
            issues.append((i, f"{todo_match.group(1)} comment should reference an issue number"))
        
        # Check for magic numbers in critical operations
        if re.search(r'retry.*=\s*\d+', line) and not re.search(r'retry.*=\s*[A-Z_]+', line):
            issues.append((i, "Magic number in retry configuration - use named constant"))
        
        # Check for Unix-specific signal usage (not cross-platform)
        if re.search(r'signal\.SIGALRM|signal\.alarm\(', line):
            issues.append((i, "Unix-specific signal usage - use cross-platform timeout mechanism"))
        
        # Check for potential Windows compatibility issues
        if re.search(r'import signal', line) and re.search(r'def.*timeout', line, re.IGNORECASE):
            issues.append((i, "Signal-based timeout may not work on Windows - use threading.Timer instead"))
    
    return issues

def main():
    """Main entry point for the reliability checker."""
    if len(sys.argv) < 2:
        print("Usage: check_reliability_patterns.py <file1> [file2] ...")
        sys.exit(1)
    
    total_issues = 0
    files_checked = 0
    
    for filepath_str in sys.argv[1:]:
        filepath = Path(filepath_str)
        
        # Skip non-Python files
        if filepath.suffix != '.py':
            continue
        
        # Skip test files for some checks
        if not filepath.exists():
            continue
            
        files_checked += 1
        issues = check_file_patterns(filepath)
        
        if issues:
            print(f"\n❌ Reliability issues in {filepath}:")
            for line_no, message in issues:
                print(f"  Line {line_no}: {message}")
            total_issues += len(issues)
    
    if total_issues > 0:
        print(f"\n❌ Found {total_issues} reliability issues in {files_checked} files")
        print("\nReliability Guidelines:")
        print("- Add input validation to public functions")
        print("- Use proper error handling for I/O operations")
        print("- Implement timeouts for long-running operations")
        print("- Use logging instead of print statements")
        print("- Avoid bare except clauses")
        print("- Make configuration values configurable")
        print("- Reference issue numbers in TODO comments")
        sys.exit(1)
    else:
        print(f"✅ No reliability issues found in {files_checked} files")
        sys.exit(0)

if __name__ == '__main__':
    main()