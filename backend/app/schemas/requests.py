from typing import Any
from pydantic import BaseModel, ConfigDict, Field

class LoginRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    email: str=Field(min_length=3,max_length=254)
    password: str=Field(min_length=1,max_length=256)

class ActionRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    payload: dict[str,Any]=Field(default_factory=dict)
