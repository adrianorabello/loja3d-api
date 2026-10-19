from typing import Dict
from pydantic import BaseModel, ConfigDict, Field


class Category(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    slug: str
    name: Dict[str, str] = Field(..., description="Localized names, e.g. {'pt-PT': '...', 'en': '...'}")
