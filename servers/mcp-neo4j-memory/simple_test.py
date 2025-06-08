#!/usr/bin/env python3
import sys
import os
sys.path.insert(0, 'src')

print("Testing MCP Compatibility Module...")

try:
    from mcp_neo4j_memory.compatibility import get_compatibility_mode
    print(f"✅ Import successful")
    print(f"✅ Default mode: {get_compatibility_mode()}")
    
    # Test Gemini mode
    os.environ['MCP_COMPATIBILITY'] = 'gemini'
    # Need to reload the module to pick up env change
    import importlib
    import mcp_neo4j_memory.compatibility
    importlib.reload(mcp_neo4j_memory.compatibility)
    from mcp_neo4j_memory.compatibility import get_compatibility_mode, is_gemini_compatible
    
    print(f"✅ Gemini mode: {get_compatibility_mode()}")
    print(f"✅ Is Gemini compatible: {is_gemini_compatible()}")
    
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()

print("Test complete!") 