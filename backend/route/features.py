from fastapi import APIRouter

router=APIRouter()
@router.post("/extract")
def extract(data:dict):
    return{
        "features":{
            "avg_balance":22000,
            "income_consistency":0.76,
            "utility_Score":0.88
        }
    }