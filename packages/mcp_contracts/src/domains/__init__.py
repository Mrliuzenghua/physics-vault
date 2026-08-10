"""MCP tool-domain registration modules."""

from .authoring import AuthoringDomain, authoring_tool_names, register_authoring_tools
from .search_knowledge import SearchKnowledgeDomain, register_search_knowledge_tools, search_knowledge_tool_names
from .import_review import ImportReviewDomain, import_review_tool_names, register_import_review_tools

__all__ = [
    "AuthoringDomain",
    "ImportReviewDomain",
    "SearchKnowledgeDomain",
    "authoring_tool_names",
    "import_review_tool_names",
    "register_authoring_tools",
    "register_import_review_tools",
    "register_search_knowledge_tools",
    "search_knowledge_tool_names",
]
