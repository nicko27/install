"""Debug utilities for field validation and dependencies"""
import logging
from typing import Any, Dict, List, Optional, Set
from dataclasses import dataclass
from datetime import datetime
import json
from textual.app import ComposeResult
from textual.containers import Container
from textual.widgets import Tree
from textual.widgets.tree import TreeNode

from ...logging import get_logger
logger = get_logger('debug')

@dataclass
class ValidationEvent:
    """Represents a validation event"""
    timestamp: datetime
    field_id: str
    value: Any
    success: bool
    message: Optional[str]
    rules_applied: List[str]

@dataclass
class DependencyEvent:
    """Represents a dependency update event"""
    timestamp: datetime
    source_field: str
    target_field: str
    old_value: Any
    new_value: Any
    rule_type: str  # 'enabled', 'visible', 'value', 'option'

class DebugManager:
    """Manages debug information and visualization"""
    
    def __init__(self):
        self.validation_events: List[ValidationEvent] = []
        self.dependency_events: List[DependencyEvent] = []
        self.field_dependencies: Dict[str, Set[str]] = {}  # field -> dependent fields
        self.field_validators: Dict[str, List[str]] = {}  # field -> validator names
        
    def add_validation_event(self, event: ValidationEvent) -> None:
        """Record validation event"""
        self.validation_events.append(event)
        logger.debug(f"Validation: {event.field_id} -> {event.success} ({event.message})")
        
    def add_dependency_event(self, event: DependencyEvent) -> None:
        """Record dependency event"""
        self.dependency_events.append(event)
        logger.debug(
            f"Dependency: {event.source_field} -> {event.target_field} "
            f"({event.rule_type}: {event.old_value} -> {event.new_value})"
        )
        
    def add_field_dependency(self, source: str, target: str) -> None:
        """Record field dependency"""
        if source not in self.field_dependencies:
            self.field_dependencies[source] = set()
        self.field_dependencies[source].add(target)
        
    def add_field_validator(self, field_id: str, validator: str) -> None:
        """Record field validator"""
        if field_id not in self.field_validators:
            self.field_validators[field_id] = []
        self.field_validators[field_id].append(validator)
        
    def get_dependency_chain(self, field_id: str) -> List[List[str]]:
        """Get all dependency chains starting from a field"""
        chains: List[List[str]] = []
        visited = set()
        
        def build_chain(current: str, chain: List[str]) -> None:
            if current in visited:
                return
            visited.add(current)
            chain.append(current)
            
            if current in self.field_dependencies:
                for dep in self.field_dependencies[current]:
                    build_chain(dep, chain.copy())
            else:
                chains.append(chain)
                
        build_chain(field_id, [])
        return chains
        
    def get_validation_stats(self, field_id: Optional[str] = None) -> Dict[str, Any]:
        """Get validation statistics"""
        events = [e for e in self.validation_events if not field_id or e.field_id == field_id]
        total = len(events)
        if not total:
            return {"total": 0, "success": 0, "failure": 0, "success_rate": 0}
            
        success = len([e for e in events if e.success])
        return {
            "total": total,
            "success": success,
            "failure": total - success,
            "success_rate": (success / total) * 100
        }
        
    def export_debug_data(self) -> str:
        """Export debug data as JSON"""
        data = {
            "validation_events": [
                {
                    "timestamp": e.timestamp.isoformat(),
                    "field_id": e.field_id,
                    "success": e.success,
                    "message": e.message,
                    "rules": e.rules_applied
                }
                for e in self.validation_events
            ],
            "dependency_events": [
                {
                    "timestamp": e.timestamp.isoformat(),
                    "source": e.source_field,
                    "target": e.target_field,
                    "type": e.rule_type,
                    "old_value": str(e.old_value),
                    "new_value": str(e.new_value)
                }
                for e in self.dependency_events
            ],
            "dependencies": {
                source: list(targets)
                for source, targets in self.field_dependencies.items()
            },
            "validators": self.field_validators
        }
        return json.dumps(data, indent=2)

class DebugView(Container):
    """Debug view widget"""
    
    def __init__(self, debug_manager: DebugManager):
        super().__init__()
        self.debug_manager = debug_manager
        
    def compose(self) -> ComposeResult:
        """Create debug view"""
        # Create dependency tree
        tree = Tree("Field Dependencies")
        self._build_dependency_tree(tree)
        yield tree
        
    def _build_dependency_tree(self, tree: Tree) -> None:
        """Build tree of field dependencies"""
        for source, targets in self.debug_manager.field_dependencies.items():
            node = tree.root.add(source)
            self._add_dependency_nodes(node, source)
            
    def _add_dependency_nodes(self, parent: TreeNode, field_id: str) -> None:
        """Add dependency nodes recursively"""
        if field_id in self.debug_manager.field_dependencies:
            for target in self.debug_manager.field_dependencies[field_id]:
                child = parent.add(f"{target}")
                # Add validation info
                if target in self.debug_manager.field_validators:
                    validators = ", ".join(self.debug_manager.field_validators[target])
                    child.add(f"Validators: {validators}")
                # Add stats
                stats = self.debug_manager.get_validation_stats(target)
                child.add(f"Success rate: {stats['success_rate']:.1f}%")
                # Continue recursion
                self._add_dependency_nodes(child, target)
