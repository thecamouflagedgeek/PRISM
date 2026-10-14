from pydantic import BaseModel, ConfigDict, Field


class TenureComparisonRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    principal: float = Field(gt=0, allow_inf_nan=False)
    annual_interest_rate_percent: float = Field(ge=0, le=100, allow_inf_nan=False)
    fees: float = Field(ge=0, allow_inf_nan=False)
    monthly_income: float = Field(gt=0, allow_inf_nan=False)
    monthly_expenses: float = Field(ge=0, allow_inf_nan=False)
    existing_monthly_obligations: float = Field(ge=0, allow_inf_nan=False)
    max_debt_to_income_ratio: float = Field(gt=0, le=1, allow_inf_nan=False)
    tenures_months: list[int] = Field(min_length=1, max_length=24)
