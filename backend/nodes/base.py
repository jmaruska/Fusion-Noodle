"""Base class for all nodes - spec-compliant."""

from typing import Dict, Any, List
from abc import ABC, abstractmethod
from ..contracts import NodeSpec

class BaseNode(ABC):
    """Abstract base class for all nodes - follows specification."""
    
    # Required class attributes per specification
    NODE_TYPE: str = ""  # Must be overridden
    NODE_CATEGORY: str = ""  # Must be overridden  
    NODE_NAME: str = ""  # Must be overridden
    NODE_DESCRIPTION: str = ""  # Must be overridden
    
    # True for nodes that are pure calculations and never touch Fusion. The
    # palette asks the backend to run these as the user edits, to show live
    # values on connected inputs (see backend/preview.py). Leave False for any
    # node that creates geometry, reads a selection, or needs the design.
    PREVIEWABLE = False

    # When the user adds a node that works on a collection, the palette also adds
    # an Atomizer before it and a Materializer after it if the graph has none
    # (see companions.py). Set False for a node that needs an array upstream
    # rather than a bare Atomizer.
    AUTO_COMPANIONS = True

    def __init__(self, node_id: str):
        """Initialize node with ID"""
        self.id = node_id
        
        # Validate that subclass has set required attributes
        if not self.NODE_TYPE:
            raise ValueError(f"{self.__class__.__name__} must define NODE_TYPE")
        if not self.NODE_CATEGORY:
            raise ValueError(f"{self.__class__.__name__} must define NODE_CATEGORY")
        if not self.NODE_NAME:
            raise ValueError(f"{self.__class__.__name__} must define NODE_NAME")
    
    @classmethod
    @abstractmethod
    def get_spec(cls) -> NodeSpec:
        """Must return node specification"""
        pass
    
    @classmethod
    def port_label(cls, name: str) -> str:
        """The label the palette shows for this node's port `name`. Use it to name a
        port in a message for the user, never the port's internal name."""
        return cls.get_spec().port_label(name)

    @abstractmethod
    def validate(self, inputs: Dict[str, Any]) -> List[str]:
        """Validate inputs. Must be implemented by subclasses."""
        pass
    
    @abstractmethod
    def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Execute node logic. Must be implemented by subclasses."""
        pass
    
    def _register_body_name(self, context: Dict[str, Any], body_name: str) -> None:
        """Register a Fusion body name under this node's ID for visibility lookup.

        Called immediately after a body is named inside the BaseFeature edit session.
        The registry survives finishEdit() because it stores names (strings), not
        Fusion object references.
        """
        node_body_names = context.get('node_body_names')
        if node_body_names is not None:
            node_body_names.setdefault(self.id, []).append(body_name)
