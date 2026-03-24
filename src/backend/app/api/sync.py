"""
资产同步 API
提供手动同步、任务查询等功能
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional
from app.core.database import get_db
from app.schemas.sync import ManualSyncResponse, SyncTaskResponse, SyncTaskList
from app.services.asset_sync import AssetSyncService

router = APIRouter()


@router.post("/tasks/manual", response_model=ManualSyncResponse)
async def manual_sync(db: Session = Depends(get_db)):
    """手动触发资产同步任务"""
    sync_service = AssetSyncService(db)
    try:
        task = sync_service.sync_from_wazuh_with_tracking("manual")
        return ManualSyncResponse(
            task_id=str(task.id),
            status=task.status,
            message="同步任务已创建"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"创建同步任务失败: {str(e)}")


@router.get("/tasks/{task_id}", response_model=SyncTaskResponse)
async def get_sync_task(task_id: str, db: Session = Depends(get_db)):
    """查询单个同步任务的详细信息"""
    from app.models.sync_task import SyncTask

    task = db.query(SyncTask).filter(SyncTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="同步任务不存在")

    return SyncTaskResponse.model_validate(task)


@router.get("/tasks", response_model=SyncTaskList)
async def list_sync_tasks(
    skip: int = 0,
    limit: int = 20,
    status: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """查询同步任务列表"""
    from app.models.sync_task import SyncTask

    query = db.query(SyncTask)

    # 按状态筛选
    if status:
        query = query.filter(SyncTask.status == status)

    # 总数
    total = query.count()

    # 分页查询，按创建时间倒序
    tasks = query.order_by(
        SyncTask.created_at.desc()
    ).offset(skip).limit(limit).all()

    return SyncTaskList(
        total=total,
        items=[SyncTaskResponse.model_validate(t) for t in tasks]
    )
