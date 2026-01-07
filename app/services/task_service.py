"""
Task Service
============
Service layer for task operations.

This service provides a clean interface between API handlers and
the task repository. For A4 (Task Ingestion), it is a thin wrapper
with NO business logic, prioritization, or scheduling.

PURPOSE:
- Abstracts repository implementation details from API layer
- Provides consistent error handling and logging
- Enables future addition of cross-cutting concerns (caching, events)
- Maintains clean separation of concerns

NON-PURPOSE (explicitly excluded):
- Task prioritization or scoring
- Scheduling or calendar integration
- Personalization or recommendations
- Any decision-making logic
"""

from typing import Optional

from app.core.logging import get_logger
from app.models.task import (
    Task,
    TaskCreate,
    TaskListFilters,
    TaskStatus,
    TaskUpdate,
)
from app.repositories.task_repository import (
    TaskNotFoundError,
    TaskRepository,
    TaskRepositoryError,
)

logger = get_logger(__name__)


class TaskServiceError(Exception):
    """Base exception for task service operations."""

    def __init__(self, message: str, internal_message: Optional[str] = None):
        self.message = message
        self.internal_message = internal_message
        super().__init__(message)


class TaskNotFoundServiceError(TaskServiceError):
    """Raised when a task is not found."""

    pass


class TaskService:
    """
    Service for task operations.
    
    Provides a clean interface for task CRUD operations.
    All methods require the authenticated user's UID for
    strict per-user isolation.
    
    Usage:
        service = TaskService()
        task = await service.create_task(uid="firebase-uid", create=TaskCreate(...))
        tasks = await service.list_tasks(uid="firebase-uid", filters=TaskListFilters(...))
    """

    def __init__(self) -> None:
        """Initialize the service with repository."""
        self._repository = TaskRepository()

    async def create_task(self, uid: str, create: TaskCreate) -> Task:
        """
        Create a new task for a user.
        
        Args:
            uid: Firebase user ID
            create: Task creation data
        
        Returns:
            Created Task
        
        Raises:
            TaskServiceError: If creation fails
        """
        try:
            task = await self._repository.create(uid, create)
            logger.info(
                "Task created via service",
                uid=uid,
                task_id=task.task_id,
            )
            return task
        except TaskRepositoryError as e:
            logger.error(
                "Task creation failed in service",
                uid=uid,
                error=e.message,
            )
            raise TaskServiceError(e.message, e.internal_message) from e

    async def get_task(self, uid: str, task_id: str) -> Optional[Task]:
        """
        Get a task by ID.
        
        Args:
            uid: Firebase user ID
            task_id: Task UUID
        
        Returns:
            Task if found, None otherwise
        """
        try:
            return await self._repository.get(uid, task_id)
        except TaskRepositoryError as e:
            logger.error(
                "Failed to get task in service",
                uid=uid,
                task_id=task_id,
                error=e.message,
            )
            raise TaskServiceError(e.message, e.internal_message) from e

    async def get_task_or_raise(self, uid: str, task_id: str) -> Task:
        """
        Get a task by ID, raising if not found.
        
        Args:
            uid: Firebase user ID
            task_id: Task UUID
        
        Returns:
            Task
        
        Raises:
            TaskNotFoundServiceError: If task doesn't exist
        """
        try:
            return await self._repository.get_or_raise(uid, task_id)
        except TaskNotFoundError as e:
            raise TaskNotFoundServiceError(e.message, e.internal_message) from e
        except TaskRepositoryError as e:
            raise TaskServiceError(e.message, e.internal_message) from e

    async def list_tasks(
        self,
        uid: str,
        filters: Optional[TaskListFilters] = None,
    ) -> list[Task]:
        """
        List tasks for a user with optional filtering.
        
        Args:
            uid: Firebase user ID
            filters: Optional filter/pagination parameters
        
        Returns:
            List of matching tasks
        """
        try:
            return await self._repository.list(uid, filters)
        except TaskRepositoryError as e:
            logger.error(
                "Failed to list tasks in service",
                uid=uid,
                error=e.message,
            )
            raise TaskServiceError(e.message, e.internal_message) from e

    async def update_task(
        self,
        uid: str,
        task_id: str,
        update: TaskUpdate,
    ) -> Task:
        """
        Partially update a task.
        
        Only provided fields are updated (PATCH semantics).
        
        Args:
            uid: Firebase user ID
            task_id: Task UUID
            update: Partial update data
        
        Returns:
            Updated Task
        
        Raises:
            TaskNotFoundServiceError: If task doesn't exist
        """
        try:
            return await self._repository.update(uid, task_id, update)
        except TaskNotFoundError as e:
            raise TaskNotFoundServiceError(e.message, e.internal_message) from e
        except TaskRepositoryError as e:
            raise TaskServiceError(e.message, e.internal_message) from e

    async def delete_task(self, uid: str, task_id: str) -> bool:
        """
        Delete a task (hard delete).
        
        Args:
            uid: Firebase user ID
            task_id: Task UUID
        
        Returns:
            True if deleted, False if task didn't exist
        """
        try:
            return await self._repository.delete(uid, task_id)
        except TaskRepositoryError as e:
            logger.error(
                "Failed to delete task in service",
                uid=uid,
                task_id=task_id,
                error=e.message,
            )
            raise TaskServiceError(e.message, e.internal_message) from e

    async def archive_task(self, uid: str, task_id: str) -> Task:
        """
        Archive a task (soft delete alternative).
        
        Sets task status to ARCHIVED instead of deleting.
        
        Args:
            uid: Firebase user ID
            task_id: Task UUID
        
        Returns:
            Updated Task with ARCHIVED status
        
        Raises:
            TaskNotFoundServiceError: If task doesn't exist
        """
        update = TaskUpdate(status=TaskStatus.ARCHIVED)
        return await self.update_task(uid, task_id, update)

    async def complete_task(self, uid: str, task_id: str) -> Task:
        """
        Mark a task as done.
        
        Args:
            uid: Firebase user ID
            task_id: Task UUID
        
        Returns:
            Updated Task with DONE status
        
        Raises:
            TaskNotFoundServiceError: If task doesn't exist
        """
        update = TaskUpdate(status=TaskStatus.DONE)
        return await self.update_task(uid, task_id, update)

    async def start_task(self, uid: str, task_id: str) -> Task:
        """
        Mark a task as in progress.
        
        Args:
            uid: Firebase user ID
            task_id: Task UUID
        
        Returns:
            Updated Task with IN_PROGRESS status
        
        Raises:
            TaskNotFoundServiceError: If task doesn't exist
        """
        update = TaskUpdate(status=TaskStatus.IN_PROGRESS)
        return await self.update_task(uid, task_id, update)

    async def count_tasks(
        self,
        uid: str,
        status: Optional[TaskStatus] = None,
    ) -> int:
        """
        Count tasks for a user.
        
        Args:
            uid: Firebase user ID
            status: Optional status filter
        
        Returns:
            Number of matching tasks
        """
        try:
            return await self._repository.count(uid, status)
        except TaskRepositoryError as e:
            raise TaskServiceError(e.message, e.internal_message) from e

    async def bulk_update_status(
        self,
        uid: str,
        task_ids: list[str],
        status: TaskStatus,
    ) -> int:
        """
        Update status for multiple tasks.
        
        Args:
            uid: Firebase user ID
            task_ids: List of task UUIDs
            status: New status to set
        
        Returns:
            Number of tasks updated
        """
        try:
            return await self._repository.bulk_update_status(uid, task_ids, status)
        except TaskRepositoryError as e:
            raise TaskServiceError(e.message, e.internal_message) from e
