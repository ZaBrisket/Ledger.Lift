from typing import Dict, Any
from uuid import UUID
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
import io

from apps.api.app.models.schedules import JobSchedule

router = APIRouter(prefix="/v1/jobs", tags=["jobs"])

@router.get("/{job_id}/schedules")
async def get_schedules(job_id: UUID)->Dict[str,Any]:
    from apps.api.app.db import get_db_session
    async with get_db_session() as s:
        res=await s.execute(select(JobSchedule).where(JobSchedule.job_id==job_id).order_by(JobSchedule.created_at))
        rows=res.scalars().all()
        return {
            "jobId": str(job_id), 
            "schedules":[
                {
                    "id":str(r.id),
                    "name":r.name,
                    "confidence":r.confidence,
                    "rowCount":r.row_count,
                    "colCount":r.col_count
                } for r in rows
            ]
        }

@router.post("/{job_id}/export")
async def export_selected(job_id: UUID, payload: Dict[str, Any])->StreamingResponse:
    try:
        import openpyxl
    except ImportError:
        raise HTTPException(status_code=500, detail="openpyxl not installed on API")
    
    sel = set(payload.get("selectedScheduleIds") or [])
    from apps.api.app.db import get_db_session
    async with get_db_session() as s:
        res=await s.execute(select(JobSchedule).where(JobSchedule.job_id==job_id))
        rows=[r for r in res.scalars().all() if str(r.id) in sel] if sel else []
    
    wb=openpyxl.Workbook()
    ws=wb.active
    ws.title="Summary"
    ws.append(["Schedule ID","Name","Confidence","Rows","Cols"])
    for r in rows:
        ws.append([str(r.id), r.name, r.confidence, r.row_count, r.col_count])
    
    mem=io.BytesIO()
    wb.save(mem)
    mem.seek(0)
    
    headers={"Content-Disposition": f'attachment; filename="export-{job_id}.xlsx"'}
    return StreamingResponse(
        mem, 
        headers=headers, 
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
