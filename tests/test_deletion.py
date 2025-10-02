import pytest
from apps.api.app.services.gdpr import initiate_job_deletion, _execute_deletion
from apps.api.app.models.costs import CostRecord

@pytest.mark.asyncio
async def test_deletion_manifest(db_session):
    # Create job and cost record
    await db_session.execute("INSERT INTO jobs(id,user_id,status) VALUES('job-del-1','user-1','completed')")
    await db_session.execute("INSERT INTO cost_records(job_id,user_id,provider,pages,cost_cents,status) VALUES('job-del-1','user-1','ocr',10,120,'COMPLETED')")
    await db_session.commit()
    
    # Initiate deletion
    manifest_id = await initiate_job_deletion(db_session, job_id="job-del-1", user_id="user-1")
    assert manifest_id is not None
    
    # Check manifest
    result = await db_session.execute("SELECT status FROM deletion_manifests WHERE id=$1", [manifest_id])
    status = result.scalar()
    assert status == "PENDING"

@pytest.mark.asyncio
async def test_deletion_removes_job_and_costs(db_session):
    # Create job
    await db_session.execute("INSERT INTO jobs(id,user_id,status) VALUES('job-del-2','user-1','completed')")
    await db_session.execute("INSERT INTO cost_records(job_id,user_id,provider,pages,cost_cents,status) VALUES('job-del-2','user-1','ocr',5,60,'COMPLETED')")
    await db_session.commit()
    
    # Execute deletion
    await _execute_deletion(db_session, job_id="job-del-2", artifacts=[])
    
    # Verify removal
    result = await db_session.execute("SELECT COUNT(*) FROM jobs WHERE id='job-del-2'")
    count = result.scalar()
    assert count == 0
    
    result = await db_session.execute("SELECT COUNT(*) FROM cost_records WHERE job_id='job-del-2'")
    count = result.scalar()
    assert count == 0
