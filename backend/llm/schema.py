from pydantic import BaseModel


class SalarySchema(BaseModel):

    employer: str | None = None

    gross_salary: float | None = None

    net_salary: float | None = None

    pf: float | None = None

    pay_period: str | None = None