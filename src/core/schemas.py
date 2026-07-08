from pydantic import BaseModel, model_validator
from datetime import datetime
from typing import Optional, Any

class EntityMetadata(BaseModel):
    """
    Standardized metadata block for all entities.
    Groups administrative fields to keep the main payload clean.
    """
    is_active: bool
    created_at: datetime
    deactivated_at: Optional[datetime] = None


class BaseMetadataResponse(BaseModel):
    """
    Mixin/Base class that automatically extracts flat DB fields 
    into a nested 'metadata' object.
    Inherit from this class for any response schema that needs metadata.
    """
    metadata: EntityMetadata

    @model_validator(mode='before')
    @classmethod
    def map_metadata(cls, data: Any) -> Any:
        """Generically maps fields to metadata for both Dicts and SQLAlchemy Models."""
        if isinstance(data, dict):
            if 'metadata' not in data:
                data['metadata'] = {
                    'is_active': data.get('is_active', True),
                    'created_at': data.get('created_at'),
                    'deactivated_at': data.get('deactivated_at')
                }
            return data
            
        # SQLAlchemy ORM Handling
        # data.__dict__ enthält alle geladenen Felder (auch Relationen wie 'address'!)
        res = {k: v for k, v in data.__dict__.items() if not k.startswith('_')}
        res['metadata'] = {
            'is_active': getattr(data, 'is_active', True),
            'created_at': getattr(data, 'created_at', None),
            'deactivated_at': getattr(data, 'deactivated_at', None)
        }
        return res