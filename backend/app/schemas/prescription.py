from pydantic import BaseModel
from typing import Optional


class DrugSearchResult(BaseModel):
    drugid: int
    name: str
    ingredient_kr: Optional[str] = None
    dosage: Optional[str] = None
    usage_method: Optional[str] = None
    duration_days: Optional[int] = None

    class Config:
        from_attributes = True


class DrugSearchResponse(BaseModel):
    code: int = 200
    result: list[DrugSearchResult]


class PrescriptionCreate(BaseModel):
    doctor_emrid: int
    drug_id: int
    form: Optional[str] = None
    dosage: Optional[str] = None
    duration_days: Optional[int] = None


class PrescriptionResponse(BaseModel):
    prescriptionid: int
    doctor_emrid: int
    drug_id: int
    drug_name: Optional[str] = None
    form: Optional[str] = None
    dosage: Optional[str] = None
    duration_days: Optional[int] = None

    class Config:
        from_attributes = True


class PrescriptionListResponse(BaseModel):
    code: int = 200
    result: list[PrescriptionResponse]
