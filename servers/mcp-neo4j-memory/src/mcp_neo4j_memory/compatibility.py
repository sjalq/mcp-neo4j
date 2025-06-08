"""
MCP Compatibility Layer

Provides dynamic schema adjustment for different AI model compatibility
while preserving all functionality.
"""

import os
from typing import Dict, Any, List, Optional, Union


# Compatibility modes
class CompatibilityMode:
    CLAUDE = "claude"        # Full schema validation (default) - Claude handles everything
    GEMINI = "gemini"       # Gemini-compatible (no minItems/maxItems/enum/defaults)
    OPENAI = "openai"       # OpenAI-optimized (no defaults in schema)
    UNIVERSAL = "universal"  # Maximum compatibility (gemini + openai)


def get_compatibility_mode() -> str:
    """Get the current compatibility mode from environment variable."""
    mode = os.environ.get('MCP_COMPATIBILITY', CompatibilityMode.CLAUDE).lower()
    
    valid_modes = [CompatibilityMode.CLAUDE, CompatibilityMode.GEMINI, 
                   CompatibilityMode.OPENAI, CompatibilityMode.UNIVERSAL]
    
    if mode not in valid_modes:
        print(f"Warning: Invalid MCP_COMPATIBILITY mode '{mode}'. Using 'claude'.")
        return CompatibilityMode.CLAUDE
    
    return mode


def is_gemini_compatible() -> bool:
    """Check if current mode requires Gemini compatibility."""
    mode = get_compatibility_mode()
    return mode in [CompatibilityMode.GEMINI, CompatibilityMode.UNIVERSAL]


def is_openai_compatible() -> bool:
    """Check if current mode requires OpenAI compatibility."""
    mode = get_compatibility_mode()
    return mode in [CompatibilityMode.OPENAI, CompatibilityMode.UNIVERSAL]


def get_array_constraints(field_name: str, min_items: Optional[int] = None, 
                         max_items: Optional[int] = None) -> Dict[str, Any]:
    """Get array constraints based on compatibility mode."""
    if is_gemini_compatible():
        # Gemini doesn't support minItems/maxItems
        return {}
    
    constraints = {}
    if min_items is not None:
        constraints["minItems"] = min_items
    if max_items is not None:
        constraints["maxItems"] = max_items
    
    return constraints


def get_enum_constraint(values: List[str]) -> Dict[str, Any]:
    """Get enum constraint based on compatibility mode."""
    if is_gemini_compatible():
        # Gemini has issues with enum constraints
        return {}
    
    return {"enum": values}


def get_default_value(field_name: str, default: Any) -> Dict[str, Any]:
    """Get default value based on compatibility mode."""
    if is_openai_compatible() or is_gemini_compatible():
        # Handle defaults in application logic instead
        return {}
    
    return {"default": default}


def get_empty_object_properties() -> Dict[str, Any]:
    """Get properties for empty objects based on compatibility mode."""
    if is_gemini_compatible():
        # Gemini requires non-empty properties for object types
        return {
            "random_string": {
                "type": "string", 
                "description": "Dummy parameter for no-parameter tools"
            }
        }
    
    return {}


def get_description(field_name: str, base_description: str, 
                   constraints: Optional[str] = None,
                   options: Optional[List[str]] = None,
                   default: Optional[Any] = None) -> str:
    """Build enhanced description with constraints and options."""
    description = base_description
    
    # Add constraints info for Gemini compatibility
    if constraints and is_gemini_compatible():
        description += f" ({constraints})"
    
    # Add options info for Gemini compatibility  
    if options and is_gemini_compatible():
        options_str = ", ".join(options)
        description += f". Valid options: {options_str}"
    
    # Add default info for OpenAI/Gemini compatibility
    if default is not None and (is_openai_compatible() or is_gemini_compatible()):
        description += f" (default: {default})"
    
    return description


# Default value handlers for application logic
class DefaultValues:
    """Default values moved from schema to application logic."""
    
    VECTOR_SEARCH_MODE = "content"
    VECTOR_SEARCH_LIMIT = 10
    VECTOR_SEARCH_THRESHOLD = 0.7


def apply_vector_search_defaults(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Apply default values for vector_search tool."""
    return {
        "query": arguments.get("query", ""),
        "mode": arguments.get("mode", DefaultValues.VECTOR_SEARCH_MODE),
        "limit": arguments.get("limit", DefaultValues.VECTOR_SEARCH_LIMIT),
        "threshold": arguments.get("threshold", DefaultValues.VECTOR_SEARCH_THRESHOLD)
    }


# Validation functions for constraints moved from schema
def validate_labels(labels: Optional[List[str]]) -> List[str]:
    """Validate labels constraints moved from schema."""
    if labels is None:
        return []
    
    if len(labels) > 3:
        raise ValueError("Labels array must contain at most 3 items")
    
    return labels


def validate_vector_search_mode(mode: str) -> str:
    """Validate vector search mode."""
    valid_modes = ["content", "observations", "identity"]
    if mode not in valid_modes:
        raise ValueError(f"Invalid mode '{mode}'. Valid options: {', '.join(valid_modes)}")
    
    return mode


def validate_vector_search_params(limit: int, threshold: float) -> tuple:
    """Validate vector search parameters."""
    if limit < 1:
        raise ValueError("Limit must be at least 1")
    
    if not (0.0 <= threshold <= 1.0):
        raise ValueError("Threshold must be between 0.0 and 1.0")
    
    return limit, threshold 