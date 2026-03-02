import os
import pytest
from polyphony.utils import get_repo_map

def test_get_repo_map_multi_lang():
    # Use the data we created in tests/data/multi_lang
    path = "tests/data/multi_lang"
    repo_map = get_repo_map(path)
    
    print(repo_map)
    
    # JS
    assert "sample.js" in repo_map
    assert "Class MyJSClass" in repo_map
    assert "Function myJSFunction(a, b)" in repo_map
    assert "ArrowFunction arrowFunc(x)" in repo_map
    
    # Go
    assert "sample.go" in repo_map
    assert "Struct MyStruct" in repo_map
    assert "Function MyGoFunction()" in repo_map
    assert "Method (m *MyStruct) MyMethod()" in repo_map
    
    # Rust
    assert "sample.rs" in repo_map
    assert "Struct MyRustStruct" in repo_map
    assert "Function my_rust_function()" in repo_map
    assert "Trait MyTrait" in repo_map
    
    # Java
    assert "sample.java" in repo_map
    assert "Class MyJavaClass" in repo_map
    assert "Method myMethod()" in repo_map
    assert "Interface MyJavaInterface" in repo_map

if __name__ == "__main__":
    test_get_repo_map_multi_lang()
