from .config_container import ConfigContainer

class GlobalConfigContainer(ConfigContainer):
    """Container for global configuration fields (like SSH)"""

    def __init__(self, config_id: str, name: str, icon: str, description: str,
                 fields_by_id: dict, config_fields: list, **kwargs):
        super().__init__(
            source_id=config_id,
            title=name,
            icon=icon,
            description=description,
            fields_by_id=fields_by_id,
            config_fields=config_fields,
            is_global=True,
            **kwargs
        )