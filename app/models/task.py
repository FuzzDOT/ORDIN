"""
Task Models
===========
Pydantic v2 models for task ingestion and validation.

These models represent task data stored in Firestore. They provide:
- Strong typing and validation for all task fields
- Required deadlines with ISO datetime format
- Bounded importance values
- Optional constraints for scheduling hints
- Status tracking through task lifecycle

STORAGE: Tasks are stored in the 'users/{uid}/tasks' Firestore subcollection,
ensuring strict per-user isolation by collection path.

NO BUSINESS LOGIC: These models are pure data containers. Prioritization,
scoring, and scheduling are handled by separate layers.
"""

from datetime import datetime
from enum import Enum
from typing import Annotated, Any, Optional
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator, model_validator


class TaskDomain(str, Enum):
    """
    Task domain/category for organization.
    
    Domains help users categorize tasks by life area.
    This is for organization only - no business logic attached.
    """

    WORK = "work"
    PERSONAL = "personal"
    ADMIN = "admin"
    HEALTH = "health"
    LEARNING = "learning"
    SOCIAL = "social"
    CREATIVE = "creative"
    OTHER = "other"


class TaskStatus(str, Enum):
    """
    Task lifecycle status.
    
    Tasks progress through these states:
    - pending: Created but not started
    - in_progress: Currently being worked on
    - done: Completed successfully
    - archived: No longer active (soft-delete equivalent)
    """

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    ARCHIVED = "archived"


class TaskConstraints(BaseModel):
    """
    Optional scheduling constraints for a task.
    
    These are hints for the scheduling layer (not implemented here).
    The ingestion layer only validates and stores them.
    """

    model_config = {"extra": "forbid"}

    earliest_start: Optional[datetime] = Field(
        default=None,
        description="Earliest datetime the task can be started (ISO 8601)",
    )
    must_be_single_block: bool = Field(
        default=False,
        description="Whether the task must be completed in one continuous block",
    )
    preferred_time_of_day: Optional[str] = Field(
        default=None,
        description="Preferred time: 'morning', 'afternoon', 'evening', or None",
        pattern="^(morning|afternoon|evening)$",
    )
    location_bound: Optional[str] = Field(
        default=None,
        description="Location constraint (e.g., 'office', 'home')",
        max_length=64,
    )

    @field_validator("earliest_start", mode="before")
    @classmethod
    def parse_earliest_start(cls, v: Any) -> Optional[datetime]:
        """Parse ISO string to datetime if needed."""
        if v is None:
            return None
        if isinstance(v, datetime):
            return v
        if isinstance(v, str):
            return datetime.fromisoformat(v.replace("Z", "+00:00"))
        raise ValueError("earliest_start must be ISO 8601 datetime string")


class Task(BaseModel):
    """
    Complete task representation for storage and retrieval.
    
    This is the canonical task model stored in Firestore.
    All fields are validated and typed.
    
    REQUIRED FIELDS:
    - task_id: Auto-generated UUID
    - user_id: Firebase UID (owner)
    - title: Task name
    - deadline: When the task must be completed
    - importance: Priority level (1-5)
    - status: Current lifecycle state
    - domain: Category/area
    - created_at/updated_at: Timestamps
    
    OPTIONAL FIELDS:
    - description: Detailed task information
    - effort_estimate_minutes: Estimated duration
    - constraints: Scheduling hints
    """

    model_config = {"extra": "forbid"}

    # Core identifiers
    task_id: str = Field(
        description="Unique task identifier (UUID)",
    )
    user_id: str = Field(
        description="Firebase UID of task owner",
        min_length=1,
    )

    # Task content
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

    # Scheduling fields
    deadline: datetime = Field(
        description="Task deadline (ISO 8601, required)",
    )
    effort_estimate_minutes: Optional[int] = Field(
        default=None,
        description="Estimated effort in minutes",
        ge=1,
        le=1440,  # Max 24 hours
    )
    importance: Annotated[int, Field(ge=1, le=5)] = Field(
        default=3,
        description="Importance level (1=lowest, 5=highest)",
    )

    # Constraints (optional scheduling hints)
    constraints: Optional[TaskConstraints] = Field(
        default=None,
        description="Optional scheduling constraints",
    )

    # Status tracking
    status: TaskStatus = Field(
        default=TaskStatus.PENDING,
        description="Task lifecycle status",
    )

    # Timestamps
    created_at: datetime = Field(
        description="Creation timestamp (ISO 8601)",
    )
    updated_at: datetime = Field(
        description="Last update timestamp (ISO 8601)",
    )

    @field_validator("deadline", "created_at", "updated_at", mode="before")
    @classmethod
    def parse_datetime(cls, v: Any) -> datetime:
        """Parse ISO string to datetime if needed."""
        if isinstance(v, datetime):
            return v
        if isinstance(v, str):
            return datetime.fromisoformat(v.replace("Z", "+00:00"))
        raise ValueError("Must be ISO 8601 datetime string")

    @model_validator(mode="after")
    def validate_earliest_start_before_deadline(self) -> "Task":
        """Ensure earliest_start is before deadline if set."""
        if self.constraints and self.constraints.earliest_start:
            if self.constraints.earliest_start >= self.deadline:
                raise ValueError("earliest_start must be before deadline")
        return self

    @classmethod
    def create_new(
        cls,
        user_id: str,
        title: str,
        deadline: datetime,
        description: Optional[str] = None,
        domain: TaskDomain = TaskDomain.OTHER,
        effort_estimate_minutes: Optional[int] = None,
        importance: int = 3,
        constraints: Optional[TaskConstraints] = None,
    ) -> "Task":
        """
        Factory method to create a new task with generated ID and timestamps.
        
        Args:
            user_id: Firebase UID of the owner
            title: Task title
            deadline: When the task must be completed
            description: Optional detailed description
            domain: Task category
            effort_estimate_minutes: Estimated duration
            importance: Priority level (1-5)
            constraints: Optional scheduling constraints
        
        Returns:
            New Task instance ready for storage
        """
        now = datetime.utcnow()
        return cls(
            task_id=str(uuid4()),
            user_id=user_id,
            title=title,
            description=description,
            domain=domain,
            deadline=deadline,
            effort_estimate_minutes=effort_estimate_minutes,
            importance=importance,
            constraints=constraints,
            status=TaskStatus.PENDING,
            created_at=now,
            updated_at=now,
        )

    def to_firestore_dict(self) -> dict[str, Any]:
        """
        Convert to Firestore-compatible dictionary.
        
        Datetimes are stored as ISO strings for compatibility.
        Nested models are converted to dicts.
        """
        data = self.model_dump(mode="json")
        return data

    @classmethod
    def from_firestore_dict(cls, data: dict[str, Any]) -> "Task":
        """
        Create Task from Firestore document data.
        
        Handles parsing of stored datetime strings and nested objects.
        """
        return cls.model_validate(data)


class TaskCreate(BaseModel):
    """
    Input model for creating a new task.
    
    This is the API contract for POST /tasks.
    Only user-provided fields are included - IDs and timestamps
    are generated server-side.
    """

    model_config = {"extra": "forbid"}

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
        description="Estimated effort in minutes",
        ge=1,
        le=1440,
    )
    importance: Annotated[int, Field(ge=1, le=5)] = Field(
        default=3,
        description="Importance level (1=lowest, 5=highest)",
    )
    constraints: Optional[TaskConstraints] = Field(
        default=None,
        description="Optional scheduling constraints",
    )

    @field_validator("deadline", mode="before")
    @classmethod
    def parse_deadline(cls, v: Any) -> datetime:
        """Parse ISO string to datetime if needed."""
        if isinstance(v, datetime):
            return v
        if isinstance(v, str):
            return datetime.fromisoformat(v.replace("Z", "+00:00"))
        raise ValueError("deadline must be ISO 8601 datetime string")

    @model_validator(mode="after")
    def validate_constraints_vs_deadline(self) -> "TaskCreate":
        """Ensure earliest_start is before deadline if set."""
        if self.constraints and self.constraints.earliest_start:
            if self.constraints.earliest_start >= self.deadline:
                raise ValueError("earliest_start must be before deadline")
        return self


class TaskUpdate(BaseModel):
    """
    Input model for partial task updates.
    
    This is the API contract for PATCH /tasks/{task_id}.
    All fields are optional - only provided fields are updated
    (PATCH semantics, no overwrites of unspecified fields).
    """

    model_config = {"extra": "forbid"}

    title: Optional[str] = Field(
        default=None,
        description="Task title",
        min_length=1,
        max_length=256,
    )
    description: Optional[str] = Field(
        default=None,
        description="Detailed task description",
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
    importance: Optional[Annotated[int, Field(ge=1, le=5)]] = Field(
        default=None,
        description="Importance level (1=lowest, 5=highest)",
    )
    constraints: Optional[TaskConstraints] = Field(
        default=None,
        description="Scheduling constraints (replaces entire constraints object)",
    )
    status: Optional[TaskStatus] = Field(
        default=None,
        description="Task lifecycle status",
    )

    @field_validator("deadline", mode="before")
    @classmethod
    def parse_deadline(cls, v: Any) -> Optional[datetime]:
        """Parse ISO string to datetime if needed."""
        if v is None:
            return None
        if isinstance(v, datetime):
            return v
        if isinstance(v, str):
            return datetime.fromisoformat(v.replace("Z", "+00:00"))
        raise ValueError("deadline must be ISO 8601 datetime string")


class TaskListFilters(BaseModel):
    """
    Query parameters for filtering task lists.
    
    These filters are applied server-side in Firestore queries.
    """

    model_config = {"extra": "forbid"}

    status: Optional[TaskStatus] = Field(
        default=None,
        description="Filter by status",
    )
    domain: Optional[TaskDomain] = Field(
        default=None,
        description="Filter by domain",
    )
    deadline_before: Optional[datetime] = Field(
        default=None,
        description="Filter tasks with deadline before this datetime",
    )
    deadline_after: Optional[datetime] = Field(
        default=None,
        description="Filter tasks with deadline after this datetime",
    )
    limit: Annotated[int, Field(ge=1, le=100)] = Field(
        default=50,
        description="Maximum number of tasks to return",
    )
    offset: Annotated[int, Field(ge=0)] = Field(
        default=0,
        description="Number of tasks to skip (for pagination)",
    )

    @field_validator("deadline_before", "deadline_after", mode="before")
    @classmethod
    def parse_deadline_filter(cls, v: Any) -> Optional[datetime]:
        """Parse ISO string to datetime if needed."""
        if v is None:
            return None
        if isinstance(v, datetime):
            return v
        if isinstance(v, str):
            return datetime.fromisoformat(v.replace("Z", "+00:00"))
        raise ValueError("Must be ISO 8601 datetime string")
