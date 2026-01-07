"""
Task Tests
==========
Unit tests for task models, repository, and service.

These tests validate:
- Task model creation and validation
- Task constraints validation
- Pydantic v2 field validation
- Service layer error handling

NOTES:
- Repository tests require Firestore emulator (integration tests)
- These are unit tests that can run without Firestore
"""

from datetime import datetime, timedelta
from uuid import uuid4

import pytest

from app.models.task import (
    Task,
    TaskConstraints,
    TaskCreate,
    TaskDomain,
    TaskListFilters,
    TaskStatus,
    TaskUpdate,
)


class TestTaskDomain:
    """Tests for TaskDomain enum."""

    def test_all_domains_exist(self) -> None:
        """Verify all expected domains are defined."""
        expected = ["work", "personal", "admin", "health", "learning", "social", "creative", "other"]
        actual = [d.value for d in TaskDomain]
        assert sorted(actual) == sorted(expected)

    def test_domain_string_values(self) -> None:
        """Domains should be lowercase strings."""
        for domain in TaskDomain:
            assert domain.value == domain.value.lower()
            assert isinstance(domain.value, str)


class TestTaskStatus:
    """Tests for TaskStatus enum."""

    def test_all_statuses_exist(self) -> None:
        """Verify all expected statuses are defined."""
        expected = ["pending", "in_progress", "done", "archived"]
        actual = [s.value for s in TaskStatus]
        assert sorted(actual) == sorted(expected)


class TestTaskConstraints:
    """Tests for TaskConstraints model."""

    def test_empty_constraints(self) -> None:
        """Constraints can be created with defaults."""
        constraints = TaskConstraints()
        assert constraints.earliest_start is None
        assert constraints.must_be_single_block is False
        assert constraints.preferred_time_of_day is None
        assert constraints.location_bound is None

    def test_constraints_with_earliest_start(self) -> None:
        """Earliest start can be set as datetime."""
        dt = datetime.utcnow() + timedelta(hours=1)
        constraints = TaskConstraints(earliest_start=dt)
        assert constraints.earliest_start == dt

    def test_constraints_with_earliest_start_string(self) -> None:
        """Earliest start can be set as ISO string."""
        iso_str = "2025-06-15T09:00:00+00:00"
        constraints = TaskConstraints(earliest_start=iso_str)
        assert constraints.earliest_start is not None
        assert constraints.earliest_start.year == 2025
        assert constraints.earliest_start.month == 6

    def test_preferred_time_of_day_validation(self) -> None:
        """Preferred time must be morning, afternoon, or evening."""
        # Valid values
        for time_of_day in ["morning", "afternoon", "evening"]:
            constraints = TaskConstraints(preferred_time_of_day=time_of_day)
            assert constraints.preferred_time_of_day == time_of_day

    def test_preferred_time_of_day_invalid(self) -> None:
        """Invalid preferred time should raise validation error."""
        with pytest.raises(ValueError):
            TaskConstraints(preferred_time_of_day="midnight")

    def test_location_bound_max_length(self) -> None:
        """Location bound has max length of 64."""
        # Valid
        constraints = TaskConstraints(location_bound="office")
        assert constraints.location_bound == "office"

        # Too long
        with pytest.raises(ValueError):
            TaskConstraints(location_bound="x" * 65)


class TestTask:
    """Tests for Task model."""

    def test_create_new_task(self) -> None:
        """Factory method creates valid task with defaults."""
        deadline = datetime.utcnow() + timedelta(days=1)
        task = Task.create_new(
            user_id="test-uid-123",
            title="Test Task",
            deadline=deadline,
        )

        assert task.task_id is not None
        assert len(task.task_id) == 36  # UUID format
        assert task.user_id == "test-uid-123"
        assert task.title == "Test Task"
        assert task.deadline == deadline
        assert task.status == TaskStatus.PENDING
        assert task.importance == 3  # Default
        assert task.domain == TaskDomain.OTHER  # Default
        assert task.description is None
        assert task.effort_estimate_minutes is None
        assert task.constraints is None
        assert task.created_at is not None
        assert task.updated_at is not None

    def test_create_new_with_all_fields(self) -> None:
        """Task can be created with all optional fields."""
        deadline = datetime.utcnow() + timedelta(days=1)
        earliest = datetime.utcnow() + timedelta(hours=1)
        constraints = TaskConstraints(
            earliest_start=earliest,
            must_be_single_block=True,
        )

        task = Task.create_new(
            user_id="test-uid-123",
            title="Complete Task",
            deadline=deadline,
            description="A detailed description",
            domain=TaskDomain.WORK,
            effort_estimate_minutes=60,
            importance=5,
            constraints=constraints,
        )

        assert task.description == "A detailed description"
        assert task.domain == TaskDomain.WORK
        assert task.effort_estimate_minutes == 60
        assert task.importance == 5
        assert task.constraints is not None
        assert task.constraints.must_be_single_block is True

    def test_title_required(self) -> None:
        """Title cannot be empty."""
        deadline = datetime.utcnow() + timedelta(days=1)
        with pytest.raises(ValueError):
            Task.create_new(
                user_id="test-uid",
                title="",  # Empty
                deadline=deadline,
            )

    def test_title_max_length(self) -> None:
        """Title has max length of 256."""
        deadline = datetime.utcnow() + timedelta(days=1)
        with pytest.raises(ValueError):
            Task.create_new(
                user_id="test-uid",
                title="x" * 257,
                deadline=deadline,
            )

    def test_importance_bounds(self) -> None:
        """Importance must be 1-5."""
        deadline = datetime.utcnow() + timedelta(days=1)

        # Valid range
        for importance in [1, 2, 3, 4, 5]:
            task = Task.create_new(
                user_id="test-uid",
                title="Test",
                deadline=deadline,
                importance=importance,
            )
            assert task.importance == importance

    def test_importance_too_low(self) -> None:
        """Importance below 1 should fail."""
        deadline = datetime.utcnow() + timedelta(days=1)
        with pytest.raises(ValueError):
            Task.create_new(
                user_id="test-uid",
                title="Test",
                deadline=deadline,
                importance=0,
            )

    def test_importance_too_high(self) -> None:
        """Importance above 5 should fail."""
        deadline = datetime.utcnow() + timedelta(days=1)
        with pytest.raises(ValueError):
            Task.create_new(
                user_id="test-uid",
                title="Test",
                deadline=deadline,
                importance=6,
            )

    def test_effort_estimate_bounds(self) -> None:
        """Effort estimate must be 1-1440 minutes."""
        deadline = datetime.utcnow() + timedelta(days=1)

        # Valid
        task = Task.create_new(
            user_id="test-uid",
            title="Test",
            deadline=deadline,
            effort_estimate_minutes=60,
        )
        assert task.effort_estimate_minutes == 60

        # Too low
        with pytest.raises(ValueError):
            Task.create_new(
                user_id="test-uid",
                title="Test",
                deadline=deadline,
                effort_estimate_minutes=0,
            )

        # Too high
        with pytest.raises(ValueError):
            Task.create_new(
                user_id="test-uid",
                title="Test",
                deadline=deadline,
                effort_estimate_minutes=1441,
            )

    def test_earliest_start_must_be_before_deadline(self) -> None:
        """Earliest start constraint must be before deadline."""
        deadline = datetime.utcnow() + timedelta(hours=1)
        earliest = datetime.utcnow() + timedelta(hours=2)  # After deadline

        with pytest.raises(ValueError) as exc_info:
            Task.create_new(
                user_id="test-uid",
                title="Test",
                deadline=deadline,
                constraints=TaskConstraints(earliest_start=earliest),
            )
        assert "earliest_start must be before deadline" in str(exc_info.value)

    def test_to_firestore_dict(self) -> None:
        """Task can be serialized to Firestore dict."""
        deadline = datetime.utcnow() + timedelta(days=1)
        task = Task.create_new(
            user_id="test-uid",
            title="Test",
            deadline=deadline,
            domain=TaskDomain.WORK,
        )

        data = task.to_firestore_dict()

        assert isinstance(data, dict)
        assert data["task_id"] == task.task_id
        assert data["user_id"] == "test-uid"
        assert data["title"] == "Test"
        assert data["domain"] == "work"
        assert data["status"] == "pending"
        assert isinstance(data["deadline"], str)  # ISO string
        assert isinstance(data["created_at"], str)

    def test_from_firestore_dict(self) -> None:
        """Task can be deserialized from Firestore dict."""
        now = datetime.utcnow()
        deadline = now + timedelta(days=1)

        data = {
            "task_id": str(uuid4()),
            "user_id": "test-uid",
            "title": "Restored Task",
            "description": "A description",
            "domain": "work",
            "deadline": deadline.isoformat(),
            "effort_estimate_minutes": 45,
            "importance": 4,
            "constraints": None,
            "status": "in_progress",
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }

        task = Task.from_firestore_dict(data)

        assert task.task_id == data["task_id"]
        assert task.title == "Restored Task"
        assert task.domain == TaskDomain.WORK
        assert task.status == TaskStatus.IN_PROGRESS
        assert task.importance == 4


class TestTaskCreate:
    """Tests for TaskCreate input model."""

    def test_minimal_create(self) -> None:
        """TaskCreate with only required fields."""
        deadline = datetime.utcnow() + timedelta(days=1)
        create = TaskCreate(
            title="New Task",
            deadline=deadline,
        )

        assert create.title == "New Task"
        assert create.deadline == deadline
        assert create.domain == TaskDomain.OTHER
        assert create.importance == 3
        assert create.description is None

    def test_full_create(self) -> None:
        """TaskCreate with all fields."""
        deadline = datetime.utcnow() + timedelta(days=1)
        create = TaskCreate(
            title="Full Task",
            description="With description",
            domain=TaskDomain.HEALTH,
            deadline=deadline,
            effort_estimate_minutes=30,
            importance=5,
            constraints=TaskConstraints(must_be_single_block=True),
        )

        assert create.title == "Full Task"
        assert create.domain == TaskDomain.HEALTH
        assert create.constraints.must_be_single_block is True

    def test_deadline_from_string(self) -> None:
        """Deadline can be provided as ISO string."""
        create = TaskCreate(
            title="Test",
            deadline="2025-12-31T23:59:59+00:00",
        )

        assert create.deadline.year == 2025
        assert create.deadline.month == 12
        assert create.deadline.day == 31


class TestTaskUpdate:
    """Tests for TaskUpdate partial update model."""

    def test_empty_update(self) -> None:
        """Update can be empty (no changes)."""
        update = TaskUpdate()
        assert update.title is None
        assert update.status is None

    def test_single_field_update(self) -> None:
        """Update can change single field."""
        update = TaskUpdate(title="New Title")
        assert update.title == "New Title"
        assert update.description is None
        assert update.status is None

    def test_status_update(self) -> None:
        """Status can be updated."""
        update = TaskUpdate(status=TaskStatus.DONE)
        assert update.status == TaskStatus.DONE

    def test_multiple_fields_update(self) -> None:
        """Multiple fields can be updated."""
        update = TaskUpdate(
            title="Updated",
            importance=5,
            status=TaskStatus.IN_PROGRESS,
        )
        assert update.title == "Updated"
        assert update.importance == 5
        assert update.status == TaskStatus.IN_PROGRESS


class TestTaskListFilters:
    """Tests for TaskListFilters query parameters."""

    def test_default_filters(self) -> None:
        """Default filters have sensible values."""
        filters = TaskListFilters()
        assert filters.status is None
        assert filters.domain is None
        assert filters.deadline_before is None
        assert filters.deadline_after is None
        assert filters.limit == 50
        assert filters.offset == 0

    def test_status_filter(self) -> None:
        """Can filter by status."""
        filters = TaskListFilters(status=TaskStatus.PENDING)
        assert filters.status == TaskStatus.PENDING

    def test_domain_filter(self) -> None:
        """Can filter by domain."""
        filters = TaskListFilters(domain=TaskDomain.WORK)
        assert filters.domain == TaskDomain.WORK

    def test_deadline_range_filter(self) -> None:
        """Can filter by deadline range."""
        start = datetime.utcnow()
        end = start + timedelta(days=7)

        filters = TaskListFilters(
            deadline_after=start,
            deadline_before=end,
        )

        assert filters.deadline_after == start
        assert filters.deadline_before == end

    def test_pagination_limits(self) -> None:
        """Pagination has bounds."""
        # Max limit is 100
        with pytest.raises(ValueError):
            TaskListFilters(limit=101)

        # Min limit is 1
        with pytest.raises(ValueError):
            TaskListFilters(limit=0)

        # Offset can't be negative
        with pytest.raises(ValueError):
            TaskListFilters(offset=-1)

    def test_valid_pagination(self) -> None:
        """Valid pagination values work."""
        filters = TaskListFilters(limit=100, offset=50)
        assert filters.limit == 100
        assert filters.offset == 50
