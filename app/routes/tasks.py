import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from app.database import get_db, TaskDB
from app.models import TaskCreate, TaskUpdate, TaskResponse
from app.config import MAX_TASKS_PER_USER

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/", response_model=List[TaskResponse])
def list_tasks(skip: int = 0, limit: int = 20, db: Session = Depends(get_db)):
    return db.query(TaskDB).offset(skip).limit(limit).all()


@router.post("/", response_model=TaskResponse, status_code=201)
def create_task(task: TaskCreate, db: Session = Depends(get_db)):
    count = db.query(TaskDB).count()
    if count >= MAX_TASKS_PER_USER:
        logger.warning("task_limit_reached", extra={"extra": {"limit": MAX_TASKS_PER_USER}})
        raise HTTPException(
            status_code=429,
            detail=f"Task limit of {MAX_TASKS_PER_USER} reached",
        )
    db_task = TaskDB(
        title=task.title,
        description=task.description,
        status=task.status.value,
    )
    db.add(db_task)
    db.commit()
    db.refresh(db_task)
    logger.info("task_created", extra={"extra": {"task_id": db_task.id, "title": db_task.title}})
    return db_task


@router.get("/{task_id}", response_model=TaskResponse)
def get_task(task_id: int, db: Session = Depends(get_db)):
    task = db.query(TaskDB).filter(TaskDB.id == task_id).first()
    if not task:
        logger.warning("task_not_found", extra={"extra": {"task_id": task_id}})
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.put("/{task_id}", response_model=TaskResponse)
def update_task(task_id: int, update: TaskUpdate, db: Session = Depends(get_db)):
    task = db.query(TaskDB).filter(TaskDB.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if update.title is not None:
        task.title = update.title
    if update.description is not None:
        task.description = update.description
    if update.status is not None:
        task.status = update.status.value
    db.commit()
    db.refresh(task)
    return task


@router.delete("/{task_id}", status_code=204)
def delete_task(task_id: int, db: Session = Depends(get_db)):
    task = db.query(TaskDB).filter(TaskDB.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    db.delete(task)
    db.commit()
