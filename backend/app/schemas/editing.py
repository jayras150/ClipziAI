"""
Editing schemas - Feature options available per plan
"""
from typing import Optional, List
from pydantic import BaseModel


class EditingOption(BaseModel):
    key: str
    name: str
    description: str
    category: str
    cost_credits: float
    min_plan: str  # free, standar, pro, team


class EditingOptionsList(BaseModel):
    options: List[EditingOption]
    locked_for_plan: List[str]  # feature keys locked for current user's plan


class ValidateEditingRequest(BaseModel):
    editing_options: dict


class ValidateEditingResponse(BaseModel):
    valid: bool
    locked_features: List[str]
    total_extra_cost: float