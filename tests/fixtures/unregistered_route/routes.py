from fastapi import APIRouter
router = APIRouter()
@router.post("/private/export")
def export_records():
    return generate_export()
