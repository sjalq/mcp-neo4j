#!/usr/bin/env python3
"""
Test script for MCP compatibility functions
"""

import os
import sys
sys.path.insert(0, 'src')

from mcp_neo4j_memory.compatibility import (
    get_compatibility_mode, is_gemini_compatible, is_openai_compatible,
    get_array_constraints, get_enum_constraint, get_default_value,
    get_empty_object_properties, get_description, apply_vector_search_defaults,
    validate_labels, validate_vector_search_mode
)

def test_claude_mode():
    """Test Claude mode (default)"""
    print("=== Testing Claude Mode ===")
    print(f"Mode: {get_compatibility_mode()}")
    print(f"Gemini compatible: {is_gemini_compatible()}")
    print(f"OpenAI compatible: {is_openai_compatible()}")
    
    # Test array constraints
    constraints = get_array_constraints("labels", min_items=1, max_items=3)
    print(f"Array constraints: {constraints}")
    
    # Test enum constraint
    enum_constraint = get_enum_constraint(["content", "observations", "identity"])
    print(f"Enum constraint: {enum_constraint}")
    
    # Test default value
    default_val = get_default_value("mode", "content")
    print(f"Default value: {default_val}")
    
    # Test empty object properties
    empty_props = get_empty_object_properties()
    print(f"Empty object properties: {empty_props}")
    
    # Test description
    desc = get_description("mode", "Search mode", options=["content", "observations"], default="content")
    print(f"Description: {desc}")
    print()

def test_gemini_mode():
    """Test Gemini compatibility mode"""
    print("=== Testing Gemini Mode ===")
    os.environ['MCP_COMPATIBILITY'] = 'gemini'
    
    # Re-import to pick up new environment variable
    import importlib
    import mcp_neo4j_memory.compatibility
    importlib.reload(mcp_neo4j_memory.compatibility)
    from mcp_neo4j_memory.compatibility import (
        get_compatibility_mode, is_gemini_compatible, is_openai_compatible,
        get_array_constraints, get_enum_constraint, get_default_value,
        get_empty_object_properties, get_description
    )
    
    print(f"Mode: {get_compatibility_mode()}")
    print(f"Gemini compatible: {is_gemini_compatible()}")
    print(f"OpenAI compatible: {is_openai_compatible()}")
    
    # Test array constraints (should be empty)
    constraints = get_array_constraints("labels", min_items=1, max_items=3)
    print(f"Array constraints: {constraints}")
    
    # Test enum constraint (should be empty)
    enum_constraint = get_enum_constraint(["content", "observations", "identity"])
    print(f"Enum constraint: {enum_constraint}")
    
    # Test default value (should be empty)
    default_val = get_default_value("mode", "content")
    print(f"Default value: {default_val}")
    
    # Test empty object properties (should have dummy)
    empty_props = get_empty_object_properties()
    print(f"Empty object properties: {empty_props}")
    
    # Test description (should include options and default)
    desc = get_description("mode", "Search mode", options=["content", "observations"], default="content")
    print(f"Description: {desc}")
    print()

def test_validation_functions():
    """Test validation functions"""
    print("=== Testing Validation Functions ===")
    
    # Test valid labels
    try:
        result = validate_labels(["Important", "Blue"])
        print(f"Valid labels: {result}")
    except Exception as e:
        print(f"Labels validation error: {e}")
    
    # Test invalid labels (too many)
    try:
        result = validate_labels(["A", "B", "C", "D"])
        print(f"Too many labels: {result}")
    except Exception as e:
        print(f"Expected error for too many labels: {e}")
    
    # Test valid mode
    try:
        result = validate_vector_search_mode("content")
        print(f"Valid mode: {result}")
    except Exception as e:
        print(f"Mode validation error: {e}")
    
    # Test invalid mode
    try:
        result = validate_vector_search_mode("invalid")
        print(f"Invalid mode: {result}")
    except Exception as e:
        print(f"Expected error for invalid mode: {e}")
    
    # Test default application
    args = {"query": "test"}
    defaults = apply_vector_search_defaults(args)
    print(f"Applied defaults: {defaults}")
    print()

if __name__ == "__main__":
    # Reset environment
    if 'MCP_COMPATIBILITY' in os.environ:
        del os.environ['MCP_COMPATIBILITY']
    
    test_claude_mode()
    test_gemini_mode()
    test_validation_functions()
    
    print("✅ All compatibility tests completed!") 