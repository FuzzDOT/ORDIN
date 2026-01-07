"""
Task API Endpoints
==================
REST API for task ingestion and management.

All endpoints require Firebase authentication (A2).
Tasks are strictly scoped to the authenticated user.

ENDPOINTS:
    POST   /api/v1/tasks                - Create a new task
    GET    /api/v1/tasks                - List tasks (with filters)
    GET    /api/v1/tasks/{task_id}      - Get a specific task
    PATCH  /api/v1/tasks/{task_id}      - Update task fields
    DELETE /api/v1/tasks/{task_id}      - Delete a task

SECURITY:
- All endpoints require valid Firebase ID token
- Users can only access their own tasks (enforced by UID scoping)
- Task IDs are UUIDs, not sequential (no enumeration attacks)
- 404 is returned for both missing and unauthorized tasks (no info leakage)

NO BUSINESS LOGIC:
- This layer handles HTTP concerns only
- No prioritization, scoring, or scheduling
- Pure ingestion and state management
"""

from datetime import datetime
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.auth import CurrentUserDep
from app.core.logging import get_logger
from app.models.task import (
    Task,
    TaskConstraints,
    TaskCreate,
    TaskDomain,
    TaskListFilters,
    TaskStatus,
    TaskUpdate,
)
from app.services.task_service import (
    TaskNotFoundServiceError,
    TaskService,
    TaskServiceError,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/tasks", tags=["tasks"])


# -----------------------------------------------------------------------------
# Response Models (versioned, stable API contracts)
# -----------------------------------------------------------------------------


class TaskConstraintsResponse(BaseModel):
    """Task constraints in API responses."""

    earliest_start: Optional[str] = Field(
        default=None, description="Earliest start datetime (ISO 8601)"
    )
    must_be_single_block: bool = Field(
        default=False, description="Must complete in one block"
    )
    preferred_time_of_day: Optional[str] = Field(
        default=None, description="Preferred time of day"
    )
    location_bound: Optional[str] = Field(
        default=None, description="Location constraint"
    )

    @classmethod
    def from_model(
        cls, constraints: Optional[TaskConstraints]
    ) -> Optional["TaskConstraintsResponse"]:
        """Create response from internal model."""
        if constraints is None:
            return None
        return cls(
            earliest_start=(
                constraints.earliest_start.isoformat()
                if constraints.earliest_start
                else None
            ),
            must_be_single_block=constraints.must_be_single_block,
            preferred_time_of_day=constraints.preferred_time_of_day,
            location_bound=constraints.location_bound,
        )


class TaskResponse(BaseModel):
    """Task in API responses."""

    task_id: str = Field(description="Unique task identifier")
    title: str = Field(description="Task title")
    description: Optional[str] = Field(default=None, description="Task description")
    domain: str = Field(description="Task domain/category")
    deadline: str = Field(description="Task deadline (ISO 8601)")
    effort_estimate_minutes: Optional[int] = Field(
        default=None, description="Estimated effort in minutes"
    )
    importance: int = Field(description="Importance level (1-5)")
    constraints: Optional[TaskConstraintsResponse] = Field(
        default=None, description="Scheduling constraints"
    )
    status: str = Field(description="Task status")
    created_at: str = Field(description="Creation timestamp (ISO 8601)")
    updated_at: str = Field(description="Last update timestamp (ISO 8601)")

    @classmethod
    def from_model(cls, task: Task) -> "TaskResponse":
        """Create response from internal model."""
        return cls(
            task_id=task.task_id,
            title=task.title,
            description=task.description,
            domain=task.domain.value,
            deadline=task.deadline.isoformat(),
            effort_estimate_minutes=task.effort_estimate_minutes,
            importance=task.importance,
            constraints=TaskConstraintsResponse.from_model(task.constraints),
            status=task.status.value,
            created_at=task.created_at.isoformat(),
            updated_at=task.updated_at.isoformat(),
        )


class TaskListResponse(BaseModel):
    """Paginated task list response."""

    tasks: list[TaskResponse] = Field(description="List of tasks")
    total: int = Field(description="Total count (for pagination)")
    limit: int = Field(description="Items per page")
    offset: int = Field(description="Current offset")


class TaskCreateRequest(BaseModel):
    """Request body for creating a task."""

    title: str = Field(
        description="Task title",
        min_length=1,
        max_length=256,
    )
    description: Optional[str] = Field(
        default=None,
        description="Detailed task description",
        max_length=4096,
    )
    domain: TaskDomain = Field(
        default=TaskDomain.OTHER,
        description="Task domain/category",
    )
    deadline: datetime = Field(
        description="Task deadline (ISO 8601, required)",
    )
    effort_estimate_minutes: Optional[int] = Field(
        default=None,
        description="Estimated effort in minutes (1-1440)",
        ge=1,
        le=1440,
    )
    importance: int = Field(
        default=3,
        description="Importance level (1=lowest, 5=highest)",
        ge=1,
        le=5,
    )
    constraints: Optional[TaskConstraints] = Field(
        default=None,
        description="Optional scheduling constraints",
    )


class TaskUpdateRequest(BaseModel):
    """Request body for updating a task."""

    title: Optional[str] = Field(
        default=None,
        description="Task title",
        min_length=1,
        max_length=256,
    )
    description: Optional[str] = Field(
        default=None,
        description="Task description",
        max_length=4096,
    )
    domain: Optional[TaskDomain] = Field(
        default=None,
        description="Task domain/category",
    )
    deadline: Optional[datetime] = Field(
        default=None,
        description="Task deadline (ISO 8601)",
    )
    effort_estimate_minutes: Optional[int] = Field(
        default=None,
        description="Estimated effort in minutes",
        ge=1,
        le=1440,
    )
    importance: Optional[int] = Field(
        default=None,
        description="Importance level (1-5)",
        ge=1,
        le=5,
    )
    constraints: Optional[TaskConstraints] = Field(
        default=None,
        description="Scheduling constraints (replaces entire object)",
    )
    status: Optional[TaskStatus] = Field(
        default=None,
        description="Task status",
    )


class BulkStatusUpdateRequest(BaseModel):
    """Request body for bulk status update."""

    task_ids: list[str] = Field(
        description="Task IDs to update",
        min_length=1,
        max_length=100,
    )
    status: TaskStatus = Field(description="New status to set")


class BulkStatusUpdateResponse(BaseModel):
    """Response for bulk status update."""

    updated_count: int = Field(description="Number of tasks updated")


# -----------------------------------------------------------------------------
# Dependency: Task Service
# -----------------------------------------------------------------------------


def get_task_service() -> TaskService:
    """Dependency to get task service instance."""
    return TaskService()


TaskServiceDep = Annotated[TaskService, Depends(get_task_service)]


# -----------------------------------------------------------------------------
# Endpoints
# -----------------------------------------------------------------------------


@router.post(
    "",
    response_model=TaskResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new task",
    description="Create a new task for the authenticated user.",
)
async def create_task(
    request: TaskCreateRequest,
    user: CurrentUserDep,
    service: TaskServiceDep,
) -> TaskResponse:
    """
    Create a new task.
    
    - **title**: Task name (required, 1-256 chars)
    - **deadline**: When the task must be completed (required, ISO 8601)
    - **description**: Detailed description (optional, max 4096 chars)
    - **domain**: Category - work, personal, admin, health, learning, social, creative, other
    - **effort_estimate_minutes**: Estimated duration in minutes (1-1440)
    - **importance**: Priority level 1-5 (default: 3)
    - **constraints**: Optional scheduling hints
    """
    try:
        # Convert request to internal model
        create = TaskCreate(
            title=request.title,
            description=request.description,
            domain=request.domain,
            deadline=request.deadline,
            effort_estimate_minutes=request.effort_estimate_minutes,
            importance=request.importance,
            constraints=request.constraints,
        )

        task = await service.create_task(user.uid, create)

        logger.info(
            "Task created via API",
            uid=user.uid,
            task_id=task.task_id,
        )

        return TaskResponse.from_model(task)

    except TaskServiceError as e:
        logger.error(
            "Failed to create task",
            uid=user.uid,
            error=e.message,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create task",
        )


@router.get(
    "",
    response_model=TaskListResponse,
    summary="List tasks",
    description="List tasks for the authenticated user with optional filtering.",
)
async def list_tasks(
    user: CurrentUserDep,
    service: TaskServiceDep,
    status_filter: Annotated[
        Optional[TaskStatus],
        Query(alias="status", description="Filter by status"),
    ] = None,
    domain: Annotated[
        Optional[TaskDomain],
        Query(description="Filter by domain"),
    ] = None,
    deadline_before: Annotated[
        Optional[datetime],
        Query(description="Filter tasks with deadline before this datetime"),
    ] = None,
    deadline_after: Annotated[
        Optional[datetime],
        Query(description="Filter tasks with deadline after this datetime"),
    ] = None,
    limit: Annotated[
        int,
        Query(description="Maximum number of tasks", ge=1, le=100),
    ] = 50,
    offset: Annotated[
        int,
        Query(description="Number of tasks to skip", ge=0),
    ] = 0,
) -> TaskListResponse:
    """
    List tasks with optional filtering and pagination.
    
    Query parameters:
    - **status**: Filter by status (pending, in_progress, done, archived)
    - **domain**: Filter by domain (work, personal, admin, etc.)
    - **deadline_before**: Filter tasks due before this datetime
    - **deadline_after**: Filter tasks due after this datetime
    - **limit**: Max results (1-100, default 50)
    - **offset**: Skip N results (for pagination)
    """
    try:
        filters = TaskListFilters(
            status=status_filter,
            domain=domain,
            deadline_before=deadline_before,
            deadline_after=deadline_after,
            limit=limit,
            offset=offset,
        )

        tasks = await service.list_tasks(user.uid, filters)

        # Get total count for pagination
        total = await service.count_tasks(user.uid, status_filter)

        return TaskListResponse(
            tasks=[TaskResponse.from_model(t) for t in tasks],
            total=total,
            limit=limit,
            offset=offset,
        )

    except TaskServiceError as e:
        logger.error(
            "Failed to list tasks",
            uid=user.uid,
            error=e.message,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list tasks",
        )


@router.get(
    "/{task_id}",
    response_model=TaskResponse,
    summary="Get a task",
    description="Get a specific task by ID.",
)
async def get_task(
    task_id: str,
    user: CurrentUserDep,
    service: TaskServiceDep,
) -> TaskResponse:
    """
    Get a specific task by ID.
    
    Returns 404 if the task doesn't exist or belongs to another user.
    """
    try:
        task = await service.get_task(user.uid, task_id)

        if task is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Task not found",
            )

        return TaskResponse.from_model(task)

    except HTTPException:
        raise
    except TaskServiceError as e:
        logger.error(
            "Failed to get task",
            uid=user.uid,
            task_id=task_id,
            error=e.message,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get task",
        )


@router.patch(
    "/{task_id}",
    response_model=TaskResponse,
    summary="Update a task",
    description="Partially update a task. Only provided fields are changed.",
)
async def update_task(
    task_id: str,
    request: TaskUpdateRequest,
    user: CurrentUserDep,
    service: TaskServiceDep,
) -> TaskResponse:
    """
    Partially update a task.
    
    Only provided fields are modified (PATCH semantics).
    Omitted fields retain their current values.
    
    Returns 404 if the task doesn't exist or belongs to another user.
    """
    try:
        # Convert request to internal model
        update = TaskUpdate(
            title=request.title,
            description=request.description,
            domain=request.domain,
            deadline=request.deadline,
            effort_estimate_minutes=request.effort_estimate_minutes,
            importance=request.importance,
            constraints=request.constraints,
            status=request.status,
        )

        task = await service.update_task(user.uid, task_id, update)

        logger.info(
            "Task updated via API",
            uid=user.uid,
            task_id=task_id,
        )

        return TaskResponse.from_model(task)

    except TaskNotFoundServiceError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )
    except TaskServiceError as e:
        logger.error(
            "Failed to update task",
            uid=user.uid,
            task_id=task_id,
            error=e.message,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update task",
        )


@router.delete(
    "/{task_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a task",
    description="Permanently delete a task.",
)
async def delete_task(
    task_id: str,
    user: CurrentUserDep,
    service: TaskServiceDep,
) -> None:
    """
    Delete a task permanently.
    
    This is a hard delete. For soft delete, use PATCH to set status to 'archived'.
    
    Returns 204 No Content on success.
    Returns 404 if the task doesn't exist or belongs to another user.
    """
    try:
        deleted = await service.delete_task(user.uid, task_id)

        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Task not found",
            )

        logger.info(
            "Task deleted via API",
            uid=user.uid,
            task_id=task_id,
        )

    except HTTPException:
        raise
    except TaskServiceError as e:
        logger.error(
            "Failed to delete task",
            uid=user.uid,
            task_id=task_id,
            error=e.message,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete task",
        )


@router.post(
    "/{task_id}/complete",
    response_model=TaskResponse,
    summary="Mark task as done",
    description="Quick action to mark a task as completed.",
)
async def complete_task(
    task_id: str,
    user: CurrentUserDep,
    service: TaskServiceDep,
) -> TaskResponse:
    """
    Mark a task as done.
    
    Convenience endpoint equivalent to PATCH with status='done'.
    """
    try:
        task = await service.complete_task(user.uid, task_id)
        return TaskResponse.from_model(task)

    except TaskNotFoundServiceError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )
    except TaskServiceError as e:
        logger.error(
            "Failed to complete task",
            uid=user.uid,
            task_id=task_id,
            error=e.message,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to complete task",
        )


@router.post(
    "/{task_id}/start",
    response_model=TaskResponse,
    summary="Start a task",
    description="Quick action to mark a task as in progress.",
)
async def start_task(
    task_id: str,
    user: CurrentUserDep,
    service: TaskServiceDep,
) -> TaskResponse:
    """
    Mark a task as in progress.
    
    Convenience endpoint equivalent to PATCH with status='in_progress'.
    """
    try:
        task = await service.start_task(user.uid, task_id)
        return TaskResponse.from_model(task)

    except TaskNotFoundServiceError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )
    except TaskServiceError as e:
        logger.error(
            "Failed to start task",
            uid=user.uid,
            task_id=task_id,
            error=e.message,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to start task",
        )


@router.post(
    "/{task_id}/archive",
    response_model=TaskResponse,
    summary="Archive a task",
    description="Soft delete by setting status to archived.",
)
async def archive_task(
    task_id: str,
    user: CurrentUserDep,
    service: TaskServiceDep,
) -> TaskResponse:
    """
    Archive a task (soft delete).
    
    Sets task status to 'archived'. Use DELETE for permanent removal.
    """
    try:
        task = await service.archive_task(user.uid, task_id)
        return TaskResponse.from_model(task)

    except TaskNotFoundServiceError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )
    except TaskServiceError as e:
        logger.error(
            "Failed to archive task",
            uid=user.uid,
            task_id=task_id,
            error=e.message,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to archive task",
        )


@router.post(
    "/bulk/status",
    response_model=BulkStatusUpdateResponse,
    summary="Bulk update task statuses",
    description="Update status for multiple tasks at once.",
)
async def bulk_update_status(
    request: BulkStatusUpdateRequest,
    user: CurrentUserDep,
    service: TaskServiceDep,
) -> BulkStatusUpdateResponse:
    """
    Update status for multiple tasks.
    
    Useful for batch operations like "complete all selected" or "archive all done".
    Maximum 100 tasks per request.
    """
    try:
        count = await service.bulk_update_status(
            user.uid,
            request.task_ids,
            request.status,
        )

        logger.info(
            "Bulk status update via API",
            uid=user.uid,
            task_count=count,
            new_status=request.status.value,
        )

        return BulkStatusUpdateResponse(updated_count=count)

    except TaskServiceError as e:
        logger.error(
            "Failed to bulk update tasks",
            uid=user.uid,
            error=e.message,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update tasks",
        )
