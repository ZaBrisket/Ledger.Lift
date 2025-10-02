import pytest
from apps.api.app.services.costs import record_ocr_cost, mark_cost_completed, reconcile_costs
from apps.api.app.models.costs import CostRecord

@pytest.mark.asyncio
async def test_cost_flow(db_session):
    # Record a cost
    await record_ocr_cost(db_session, job_id="job-cost-1", user_id="user-1", pages=10)
    
    result = await db_session.execute("SELECT status FROM cost_records WHERE job_id='job-cost-1'")
    status = result.scalar()
    assert status == "PENDING"
    
    # Mark completed
    await mark_cost_completed(db_session, job_id="job-cost-1")
    
    result = await db_session.execute("SELECT status FROM cost_records WHERE job_id='job-cost-1'")
    status = result.scalar()
    assert status == "COMPLETED"

@pytest.mark.asyncio
async def test_stale_cost_detection(db_session):
    # Create old PENDING record
    await db_session.execute("INSERT INTO cost_records(job_id,user_id,provider,pages,cost_cents,status,created_at) VALUES('job-stale','user-1','ocr',10,120,'PENDING',NOW() - INTERVAL '10 minutes')")
    await db_session.commit()
    
    stale = await reconcile_costs(db_session)
    assert len(stale) == 1
    assert stale[0]["job_id"] == "job-stale"
