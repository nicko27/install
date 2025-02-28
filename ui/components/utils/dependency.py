"""Enhanced dependency management for fields"""
from typing import Any, Callable, Dict, List, Optional, Union
from dataclasses import dataclass
import operator

@dataclass
class Condition:
    """Represents a single condition in a dependency rule"""
    field: str
    operator: str
    value: Any
    
    def evaluate(self, fields_by_id: Dict[str, Any]) -> bool:
        """Evaluate the condition"""
        if self.field not in fields_by_id:
            return False
            
        field_value = fields_by_id[self.field].get_value()
        
        ops = {
            '==': operator.eq,
            '!=': operator.ne,
            '>': operator.gt,
            '>=': operator.ge,
            '<': operator.lt,
            '<=': operator.le,
            'in': lambda x, y: x in y,
            'not_in': lambda x, y: x not in y,
            'contains': lambda x, y: y in x if x else False,
            'starts_with': lambda x, y: x.startswith(y) if x else False,
            'ends_with': lambda x, y: x.endswith(y) if x else False,
        }
        
        if self.operator not in ops:
            return False
            
        try:
            return ops[self.operator](field_value, self.value)
        except Exception:
            return False

class DependencyRule:
    """Complex dependency rule with multiple conditions"""
    
    def __init__(self):
        self.conditions: List[Union[Condition, str, 'DependencyRule']] = []
        
    @classmethod
    def from_dict(cls, config: Dict) -> 'DependencyRule':
        """Create rule from configuration dictionary"""
        rule = cls()
        
        if 'and' in config:
            rule.conditions.extend([cls.from_dict(c) if isinstance(c, dict) else Condition(**c) 
                                 for c in config['and']])
            rule.operator = all
        elif 'or' in config:
            rule.conditions.extend([cls.from_dict(c) if isinstance(c, dict) else Condition(**c) 
                                 for c in config['or']])
            rule.operator = any
        elif 'not' in config:
            subrule = cls.from_dict(config['not']) if isinstance(config['not'], dict) \
                     else Condition(**config['not'])
            rule.conditions.append(subrule)
            rule.operator = lambda x: not x[0]
        else:
            # Single condition
            return Condition(**config)
            
        return rule
        
    def evaluate(self, fields_by_id: Dict[str, Any]) -> bool:
        """Evaluate the entire rule"""
        results = []
        for condition in self.conditions:
            if isinstance(condition, Condition):
                results.append(condition.evaluate(fields_by_id))
            elif isinstance(condition, DependencyRule):
                results.append(condition.evaluate(fields_by_id))
            elif isinstance(condition, str) and condition.lower() in ('and', 'or', 'not'):
                continue
            else:
                results.append(False)
                
        return self.operator(results)

class DependencyManager:
    """Manages field dependencies and visibility rules"""
    
    def __init__(self, fields_by_id: Dict[str, Any]):
        self.fields_by_id = fields_by_id
        self.enabled_rules: Dict[str, DependencyRule] = {}
        self.visible_rules: Dict[str, DependencyRule] = {}
        self.value_dependencies: Dict[str, List[str]] = {}
        self.option_dependencies: Dict[str, List[str]] = {}
        
    def add_enabled_rule(self, field_id: str, rule_config: Dict):
        """Add enabled_if rule"""
        self.enabled_rules[field_id] = DependencyRule.from_dict(rule_config)
        
    def add_visible_rule(self, field_id: str, rule_config: Dict):
        """Add visible_if rule"""
        self.visible_rules[field_id] = DependencyRule.from_dict(rule_config)
        
    def add_value_dependency(self, source_field: str, target_field: str):
        """Add value dependency between fields"""
        if source_field not in self.value_dependencies:
            self.value_dependencies[source_field] = []
        self.value_dependencies[source_field].append(target_field)
        
    def add_option_dependency(self, source_field: str, target_field: str):
        """Add option dependency between fields"""
        if source_field not in self.option_dependencies:
            self.option_dependencies[source_field] = []
        self.option_dependencies[source_field].append(target_field)
        
    def update_field_state(self, field_id: str) -> None:
        """Update state of all dependent fields when a field changes"""
        # Update enabled state
        for dep_field_id, rule in self.enabled_rules.items():
            field = self.fields_by_id.get(dep_field_id)
            if field:
                enabled = rule.evaluate(self.fields_by_id)
                field.update_enabled_state(enabled)
                
        # Update visibility
        for dep_field_id, rule in self.visible_rules.items():
            field = self.fields_by_id.get(dep_field_id)
            if field:
                visible = rule.evaluate(self.fields_by_id)
                field.update_visibility(visible)
                
        # Update dependent values
        if field_id in self.value_dependencies:
            for dep_field_id in self.value_dependencies[field_id]:
                field = self.fields_by_id.get(dep_field_id)
                if field:
                    field.refresh_value()
                    
        # Update dependent options
        if field_id in self.option_dependencies:
            for dep_field_id in self.option_dependencies[field_id]:
                field = self.fields_by_id.get(dep_field_id)
                if field:
                    field.refresh_options()
