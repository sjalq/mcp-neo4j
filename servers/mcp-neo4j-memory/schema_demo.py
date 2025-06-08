#!/usr/bin/env python3
"""
Demo script showing schema differences between compatibility modes
"""
import sys
import os
import json
sys.path.insert(0, 'src')

def show_schema_differences():
    print("🔍 MCP Schema Compatibility Demo")
    print("=" * 50)
    
    # Test Claude mode (default)
    print("\n📋 CLAUDE MODE (Default - Full Validation)")
    print("-" * 40)
    
    if 'MCP_COMPATIBILITY' in os.environ:
        del os.environ['MCP_COMPATIBILITY']
    
    try:
        from mcp_neo4j_memory.compatibility import (
            get_compatibility_mode, get_array_constraints, get_enum_constraint,
            get_default_value, get_empty_object_properties, get_description
        )
        
        print(f"Mode: {get_compatibility_mode()}")
        
        # Show labels schema
        labels_schema = {
            "type": "array",
            "items": {"type": "string"},
            **get_array_constraints("labels", min_items=1, max_items=3),
            "description": get_description("labels", "Array of 1-3 labels", constraints="1-3 items")
        }
        print(f"Labels schema: {json.dumps(labels_schema, indent=2)}")
        
        # Show mode schema  
        mode_schema = {
            "type": "string",
            **get_enum_constraint(["content", "observations", "identity"]),
            "description": get_description("mode", "Search mode", options=["content", "observations"], default="content"),
            **get_default_value("mode", "content")
        }
        print(f"Mode schema: {json.dumps(mode_schema, indent=2)}")
        
        # Show empty object
        empty_props = get_empty_object_properties()
        print(f"Empty object properties: {json.dumps(empty_props, indent=2)}")
        
    except Exception as e:
        print(f"❌ Claude mode error: {e}")
    
    # Test Gemini mode
    print("\n🤖 GEMINI MODE (Simplified for Compatibility)")
    print("-" * 40)
    
    os.environ['MCP_COMPATIBILITY'] = 'gemini'
    
    try:
        # Reload module to pick up env change
        import importlib
        import mcp_neo4j_memory.compatibility
        importlib.reload(mcp_neo4j_memory.compatibility)
        
        from mcp_neo4j_memory.compatibility import (
            get_compatibility_mode, get_array_constraints, get_enum_constraint,
            get_default_value, get_empty_object_properties, get_description
        )
        
        print(f"Mode: {get_compatibility_mode()}")
        
        # Show labels schema (should have no constraints)
        labels_schema = {
            "type": "array",
            "items": {"type": "string"},
            **get_array_constraints("labels", min_items=1, max_items=3),
            "description": get_description("labels", "Array of 1-3 labels", constraints="1-3 items")
        }
        print(f"Labels schema: {json.dumps(labels_schema, indent=2)}")
        
        # Show mode schema (should have no enum/default)
        mode_schema = {
            "type": "string",
            **get_enum_constraint(["content", "observations", "identity"]),
            "description": get_description("mode", "Search mode", options=["content", "observations"], default="content"),
            **get_default_value("mode", "content")
        }
        print(f"Mode schema: {json.dumps(mode_schema, indent=2)}")
        
        # Show empty object (should have dummy property)
        empty_props = get_empty_object_properties()
        print(f"Empty object properties: {json.dumps(empty_props, indent=2)}")
        
    except Exception as e:
        print(f"❌ Gemini mode error: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n✅ Schema demo complete!")
    print("\nKey Differences:")
    print("- Claude mode: Full constraints (minItems, maxItems, enum, default)")
    print("- Gemini mode: Constraints moved to descriptions, dummy properties added")

if __name__ == "__main__":
    show_schema_differences() 