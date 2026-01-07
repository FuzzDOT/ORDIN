"""
Task Repository
===============
Firestore repository for task documents.

This repository provides type-safe CRUD operations for user tasks
stored in Firestore subcollections. It handles:
- Per-user task isolation via subcollection path
- Pagination and filtering for task lists
- Partial updates (PATCH semantics) without overwriting unspecified fields
- Idempotent writes for reliability
- Hard delete (consistent with documented behavior)
- Consistent error handling and logging

COLLECTION STRUCTURE:
    Collection: users/{uid}/tasks
    Document ID: {task_id} (UUID)
    Fields: See Task model

This structure ensures strict per-user isolation at the Firestore
path level - users can only access documents in their own subcollection.

ASYNC SAFETY:
Firestore SDK operations are synchronous. This repository uses
asyncio.to_thread() to run them in a thread pool, ensuring
non-blocking behavior in the async FastAPI context.

INDEXING REQUIREMENTS:
For efficient queries, create composite indexes on:
- users/{uid}/tasks: (status ASC, deadline ASC)
- users/{uid}/tasks: (domain ASC, deadline ASC)
- users/{uid}/tasks: (deadline ASC)
"""

import asyncio
from datetime import datetime
from typing import Any, Optional

from google.cloud import firestore

from app.core.logging import get_logger
from app.db import FirestoreError, get_firestore_client
from app.models.task import (
    Task,
    TaskCreate,
    TaskDomain,
    TaskListFilters,
    TaskStatus,
    TaskUpdate,
)

logger = get_logger(__name__)

# Firestore collection names
USERS_COLLECTION = "users"
TASKS_SUBCOLLECTION = "tasks"


class TaskRepositoryError(FirestoreError):
    """Base exception for task repository operations."""

    pass


class TaskNotFoundError(TaskRepositoryError):
    """Raised when a task is not found."""

    pass


class TaskRepository:
    """
    Repository for task Firestore operations.
    
    All methods are async-safe and handle Firestore operations
    in a thread pool to avoid blocking the event loop.
    
    Tasks are stored in per-user subcollections for strict isolation:
    users/{uid}/tasks/{task_id}
    
    Usage:
        repo = TaskRepository()
        task = await repo.create(uid="firebase-uid", create=TaskCreate(...))
        tasks = await repo.list(uid="firebase-uid", filters=TaskListFilters(...))
    """

    def __init__(self) -> None:
        """Initialize the repository with Firestore client."""
        self._db = get_firestore_client()

    def _get_tasks_collection(self, uid: str):
        """Get the tasks subcollection reference for a user."""
        return self._db.collection(USERS_COLLECTION).document(uid).collection(
            TASKS_SUBCOLLECTION
        )

    def _get_task_ref(self, uid: str, task_id: str):
        """Get a document reference for a specific task."""
        return self._get_tasks_collection(uid).document(task_id)

    async def create(self, uid: str, create: TaskCreate) -> Task:
        """
        Create a new task for a user.
        
        Generates task_id and timestamps server-side.
        This operation is idempotent if called with the same task_id.
        
        Args:
            uid: Firebase user ID
            create: Task creation data
        
        Returns:
            Created Task with generated ID and timestamps
        """
        try:
            # Create task with generated ID and timestamps
            task = Task.create_new(
                user_id=uid,
                title=create.title,
                deadline=create.deadline,
                description=create.description,
                domain=create.domain,
                effort_estimate_minutes=create.effort_estimate_minutes,
                importance=create.importance,
                constraints=create.constraints,
            )

            doc_ref = self._get_task_ref(uid, task.task_id)
            await asyncio.to_thread(doc_ref.set, task.to_firestore_dict())

            logger.info(
                "Created new task",
                uid=uid,
                task_id=task.task_id,
                title=task.title,
            )
            return task

        except Exception as e:
            logger.error(
                "Failed to create task",
                uid=uid,
                error=str(e),
                error_type=type(e).__name__,
            )
            raise TaskRepositoryError(
                "Failed to create task",
                f"Firestore create failed for uid={uid}: {e}",
            ) from e

    async def get(self, uid: str, task_id: str) -> Optional[Task]:
        """
        Get a task by ID for a specific user.
        
        Args:
            uid: Firebase user ID
            task_id: Task UUID
        
        Returns:
            Task if found, None otherwise
        """
        try:
            doc_ref = self._get_task_ref(uid, task_id)
            doc = await asyncio.to_thread(doc_ref.get)

            if not doc.exists:
                logger.debug("Task not found", uid=uid, task_id=task_id)
                return None

            data = doc.to_dict()
            if data is None:
                logger.warning("Task document exists but has no data", uid=uid, task_id=task_id)
                return None

            task = Task.from_firestore_dict(data)
            logger.debug("Task retrieved", uid=uid, task_id=task_id)
            return task

        except Exception as e:
            logger.error(
                "Failed to get task",
                uid=uid,
                task_id=task_id,
                error=str(e),
                error_type=type(e).__name__,
            )
            raise TaskRepositoryError(
                "Failed to retrieve task",
                f"Firestore get failed for uid={uid}, task_id={task_id}: {e}",
            ) from e

    async def get_or_raise(self, uid: str, task_id: str) -> Task:
        """
        Get a task by ID, raising if not found.
        
        Use this when the task must exist (e.g., for updates).
        
        Args:
            uid: Firebase user ID
            task_id: Task UUID
        
        Returns:
            Task
        
        Raises:
            TaskNotFoundError: If task doesn't exist
        """
        task = await self.get(uid, task_id)
        if task is None:
            raise TaskNotFoundError(
                "Task not found",
                f"No task with id={task_id} for uid={uid}",
            )
        return task

    async def list(
        self,
        uid: str,
        filters: Optional[TaskListFilters] = None,
    ) -> list[Task]:
        """
        List tasks for a user with optional filtering and pagination.
        
        Args:
            uid: Firebase user ID
            filters: Optional filter/pagination parameters
        
        Returns:
            List of matching tasks, ordered by deadline
        """
        if filters is None:
            filters = TaskListFilters()

        try:
            # Build query with filters
            query = self._get_tasks_collection(uid)

            # Apply status filter
            if filters.status is not None:
                query = query.where("status", "==", filters.status.value)

            # Apply domain filter
            if filters.domain is not None:
                query = query.where("domain", "==", filters.domain.value)

            # Apply deadline range filters
            if filters.deadline_after is not None:
                query = query.where(
                    "deadline", ">=", filters.deadline_after.isoformat()
                )

            if filters.deadline_before is not None:
                query = query.where(
                    "deadline", "<=", filters.deadline_before.isoformat()
                )

            # Order by deadline (default sort)
            query = query.order_by("deadline", direction=firestore.Query.ASCENDING)

            # Apply pagination
            if filters.offset > 0:
                query = query.offset(filters.offset)

            query = query.limit(filters.limit)

            # Execute query
            docs = await asyncio.to_thread(query.get)

            tasks: list[Task] = []
            for doc in docs:
                data = doc.to_dict()
                if data is not None:
                    tasks.append(Task.from_firestore_dict(data))

            logger.debug(
                "Listed tasks",
                uid=uid,
                count=len(tasks),
                filters={
                    "status": filters.status.value if filters.status else None,
                    "domain": filters.domain.value if filters.domain else None,
                    "limit": filters.limit,
                    "offset": filters.offset,
                },
            )
            return tasks

        except Exception as e:
            logger.error(
                "Failed to list tasks",
                uid=uid,
                error=str(e),
                error_type=type(e).__name__,
            )
            raise TaskRepositoryError(
                "Failed to list tasks",
                f"Firestore query failed for uid={uid}: {e}",
            ) from e

    async def update(
        self,
        uid: str,
        task_id: str,
        update: TaskUpdate,
    ) -> Task:
        """
        Partially update a task.
        
        Only fields present in the update are modified.
        Unspecified fields remain unchanged (PATCH semantics).
        
        Args:
            uid: Firebase user ID
            task_id: Task UUID
            update: Partial update data
        
        Returns:
            Updated Task
        
        Raises:
            TaskNotFoundError: If task doesn't exist
        """
        try:
            doc_ref = self._get_task_ref(uid, task_id)
            doc = await asyncio.to_thread(doc_ref.get)

            if not doc.exists:
                raise TaskNotFoundError(
                    "Task not found",
                    f"No task with id={task_id} for uid={uid}",
                )

            # Build update dict with only provided fields
            update_data = update.model_dump(exclude_none=True, mode="json")

            if not update_data:
                # No fields to update, return current task
                data = doc.to_dict()
                if data is None:
                    raise TaskNotFoundError(
                        "Task data missing",
                        f"Task document exists but has no data: task_id={task_id}",
                    )
                return Task.from_firestore_dict(data)

            # Add updated_at timestamp
            update_data["updated_at"] = datetime.utcnow().isoformat()

            # Perform partial update
            await asyncio.to_thread(doc_ref.update, update_data)

            # Fetch and return updated document
            updated_doc = await asyncio.to_thread(doc_ref.get)
            updated_data = updated_doc.to_dict()
            if updated_data is None:
                raise TaskRepositoryError(
                    "Failed to verify update",
                    f"Updated document has no data: task_id={task_id}",
                )
            updated_task = Task.from_firestore_dict(updated_data)

            logger.info(
                "Updated task",
                uid=uid,
                task_id=task_id,
                updated_fields=list(update_data.keys()),
            )
            return updated_task

        except TaskNotFoundError:
            raise
        except Exception as e:
            logger.error(
                "Failed to update task",
                uid=uid,
                task_id=task_id,
                error=str(e),
                error_type=type(e).__name__,
            )
            raise TaskRepositoryError(
                "Failed to update task",
                f"Firestore update failed for uid={uid}, task_id={task_id}: {e}",
            ) from e

    async def delete(self, uid: str, task_id: str) -> bool:
        """
        Delete a task (hard delete).
        
        This permanently removes the task document. For soft-delete
        semantics, use update() to set status to ARCHIVED instead.
        
        Args:
            uid: Firebase user ID
            task_id: Task UUID
        
        Returns:
            True if deleted, False if task didn't exist
        """
        try:
            doc_ref = self._get_task_ref(uid, task_id)
            doc = await asyncio.to_thread(doc_ref.get)

            if not doc.exists:
                logger.debug(
                    "Attempted to delete non-existent task",
                    uid=uid,
                    task_id=task_id,
                )
                return False

            await asyncio.to_thread(doc_ref.delete)

            logger.info(
                "Deleted task",
                uid=uid,
                task_id=task_id,
            )
            return True

        except Exception as e:
            logger.error(
                "Failed to delete task",
                uid=uid,
                task_id=task_id,
                error=str(e),
                error_type=type(e).__name__,
            )
            raise TaskRepositoryError(
                "Failed to delete task",
                f"Firestore delete failed for uid={uid}, task_id={task_id}: {e}",
            ) from e

    async def count(
        self,
        uid: str,
        status: Optional[TaskStatus] = None,
    ) -> int:
        """
        Count tasks for a user, optionally filtered by status.
        
        Note: This performs a full collection scan if no index exists.
        For high-volume usage, consider maintaining a counter document.
        
        Args:
            uid: Firebase user ID
            status: Optional status filter
        
        Returns:
            Number of matching tasks
        """
        try:
            query = self._get_tasks_collection(uid)

            if status is not None:
                query = query.where("status", "==", status.value)

            # Use select([]) to only retrieve document IDs, not full documents
            query = query.select([])
            docs = await asyncio.to_thread(query.get)

            count = len(list(docs))
            logger.debug(
                "Counted tasks",
                uid=uid,
                status=status.value if status else None,
                count=count,
            )
            return count

        except Exception as e:
            logger.error(
                "Failed to count tasks",
                uid=uid,
                error=str(e),
                error_type=type(e).__name__,
            )
            raise TaskRepositoryError(
                "Failed to count tasks",
                f"Firestore count failed for uid={uid}: {e}",
            ) from e

    async def exists(self, uid: str, task_id: str) -> bool:
        """
        Check if a task exists.
        
        Args:
            uid: Firebase user ID
            task_id: Task UUID
        
        Returns:
            True if task exists
        """
        try:
            doc_ref = self._get_task_ref(uid, task_id)
            doc = await asyncio.to_thread(doc_ref.get)
            return doc.exists

        except Exception as e:
            logger.error(
                "Failed to check task existence",
                uid=uid,
                task_id=task_id,
                error=str(e),
                error_type=type(e).__name__,
            )
            raise TaskRepositoryError(
                "Failed to check task existence",
                f"Firestore exists check failed: {e}",
            ) from e

    async def bulk_update_status(
        self,
        uid: str,
        task_ids: list[str],
        status: TaskStatus,
    ) -> int:
        """
        Update status for multiple tasks at once.
        
        Uses batched writes for efficiency.
        
        Args:
            uid: Firebase user ID
            task_ids: List of task UUIDs to update
            status: New status to set
        
        Returns:
            Number of tasks updated
        """
        if not task_ids:
            return 0

        try:
            batch = self._db.batch()
            now = datetime.utcnow().isoformat()
            update_count = 0

            for task_id in task_ids:
                doc_ref = self._get_task_ref(uid, task_id)
                batch.update(doc_ref, {
                    "status": status.value,
                    "updated_at": now,
                })
                update_count += 1

            await asyncio.to_thread(batch.commit)

            logger.info(
                "Bulk updated task statuses",
                uid=uid,
                task_ids=task_ids,
                new_status=status.value,
                count=update_count,
            )
            return update_count

        except Exception as e:
            logger.error(
                "Failed to bulk update task statuses",
                uid=uid,
                task_ids=task_ids,
                error=str(e),
                error_type=type(e).__name__,
            )
            raise TaskRepositoryError(
                "Failed to bulk update task statuses",
                f"Firestore batch update failed for uid={uid}: {e}",
            ) from e
