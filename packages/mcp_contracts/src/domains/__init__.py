"""MCP tool-domain registration modules."""

from .authoring import AuthoringDomain, authoring_tool_names, register_authoring_tools
from .management import ManagementDomain, management_tool_names, register_management_tools
from .operations import OperationsDomain, operations_tool_names, register_operations_tools
from .search_knowledge import SearchKnowledgeDomain, register_search_knowledge_tools, search_knowledge_tool_names
from .import_review import ImportReviewDomain, import_review_tool_names, register_import_review_tools

__all__ = [
    "AuthoringDomain",
    "ImportReviewDomain",
    "ManagementDomain",
    "OperationsDomain",
    "SearchKnowledgeDomain",
    "authoring_tool_names",
    "import_review_tool_names",
    "management_tool_names",
    "operations_tool_names",
    "register_authoring_tools",
    "register_import_review_tools",
    "register_management_tools",
    "register_operations_tools",
    "register_search_knowledge_tools",
    "search_knowledge_tool_names",
]
