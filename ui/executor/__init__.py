"""
Module d'exécution des plugins, avec support local et SSH.
"""

from .execution_screen import ExecutionScreen
from .execution_widget import ExecutionWidget
from .plugin_container import PluginContainer

__all__ = ['ExecutionScreen', 'ExecutionWidget', 'PluginContainer']