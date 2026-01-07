"""
User Profile Tests
==================
Tests for user profile API endpoints, service, and repository.

These tests cover:
- Profile auto-creation on first access
- Partial updates (PATCH semantics)
- Preferences updates
- Response format validation
- Error handling
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.auth.context import UserContext
from app.models import (
    DayOfWeek,
    FocusBlockLength,
    TimeOfDay,
    UserPreferences,
    UserPreferencesUpdate,
    UserProfile,
    UserProfileUpdate,
)


# -----------------------------------------------------------------------------
# Model Tests
# -----------------------------------------------------------------------------


class TestTimeOfDay:
    """Tests for TimeOfDay model."""

    def test_valid_time(self):
        """Test valid time creation."""
        t = TimeOfDay(hour=7, minute=30)
        assert t.hour == 7
        assert t.minute == 30
        assert str(t) == "07:30"

    def test_default_minute(self):
        """Test default minute value."""
        t = TimeOfDay(hour=9)
        assert t.minute == 0

    def test_invalid_hour_high(self):
        """Test validation for hour > 23."""
        with pytest.raises(ValidationError):
            TimeOfDay(hour=24, minute=0)

    def test_invalid_hour_low(self):
        """Test validation for hour < 0."""
        with pytest.raises(ValidationError):
            TimeOfDay(hour=-1, minute=0)

    def test_invalid_minute_high(self):
        """Test validation for minute > 59."""
        with pytest.raises(ValidationError):
            TimeOfDay(hour=12, minute=60)

    def test_to_time(self):
        """Test conversion to Python time."""
        t = TimeOfDay(hour=14, minute=45)
        from datetime import time
        assert t.to_time() == time(14, 45)

    def test_from_time(self):
        """Test creation from Python time."""
        from datetime import time
        t = TimeOfDay.from_time(time(8, 15))
        assert t.hour == 8
        assert t.minute == 15


class TestUserPreferences:
    """Tests for UserPreferences model."""

    def test_default_values(self):
        """Test that defaults are sensible."""
        prefs = UserPreferences()
        
        assert prefs.timezone == "UTC"
        assert prefs.typical_wake_time.hour == 7
        assert prefs.typical_sleep_time.hour == 23
        assert len(prefs.preferred_focus_block_lengths) == 1
        assert prefs.preferred_focus_block_lengths[0] == FocusBlockLength.MEDIUM
        assert len(prefs.preferred_working_days) == 5
        assert DayOfWeek.SATURDAY not in prefs.preferred_working_days
        assert prefs.notifications_enabled is True
        assert prefs.quiet_hours_start is None

    def test_custom_values(self):
        """Test custom preference values."""
        prefs = UserPreferences(
            timezone="America/New_York",
            typical_wake_time=TimeOfDay(hour=6, minute=30),
            preferred_focus_block_lengths=[FocusBlockLength.SHORT, FocusBlockLength.LONG],
            preferred_working_days=[DayOfWeek.MONDAY, DayOfWeek.TUESDAY],
        )
        
        assert prefs.timezone == "America/New_York"
        assert prefs.typical_wake_time.hour == 6
        assert len(prefs.preferred_focus_block_lengths) == 2

    def test_deduplicate_working_days(self):
        """Test that duplicate days are removed."""
        prefs = UserPreferences(
            preferred_working_days=[
                DayOfWeek.MONDAY,
                DayOfWeek.MONDAY,
                DayOfWeek.TUESDAY,
            ]
        )
        assert len(prefs.preferred_working_days) == 2

    def test_deduplicate_focus_lengths(self):
        """Test that duplicate focus lengths are removed."""
        prefs = UserPreferences(
            preferred_focus_block_lengths=[
                FocusBlockLength.SHORT,
                FocusBlockLength.SHORT,
                FocusBlockLength.LONG,
            ]
        )
        assert len(prefs.preferred_focus_block_lengths) == 2


class TestUserProfile:
    """Tests for UserProfile model."""

    def test_create_default(self):
        """Test default profile creation."""
        profile = UserProfile.create_default(
            uid="test-uid-123",
            email="test@example.com",
        )
        
        assert profile.uid == "test-uid-123"
        assert profile.email == "test@example.com"
        assert profile.display_name is None
        assert profile.onboarding_completed is False
        assert profile.schema_version == 1
        assert isinstance(profile.preferences, UserPreferences)
        assert isinstance(profile.created_at, datetime)

    def test_to_firestore_dict(self):
        """Test Firestore serialization."""
        profile = UserProfile.create_default(uid="test-uid")
        data = profile.to_firestore_dict()
        
        assert isinstance(data, dict)
        assert data["uid"] == "test-uid"
        assert "preferences" in data
        assert isinstance(data["preferences"], dict)

    def test_from_firestore_dict(self):
        """Test Firestore deserialization."""
        data = {
            "uid": "test-uid",
            "email": "test@example.com",
            "display_name": "Test User",
            "preferences": {
                "timezone": "UTC",
                "typical_wake_time": {"hour": 7, "minute": 0},
                "typical_sleep_time": {"hour": 23, "minute": 0},
                "preferred_focus_block_lengths": [45],
                "preferred_working_days": ["monday", "tuesday"],
                "notifications_enabled": True,
            },
            "onboarding_completed": True,
            "schema_version": 1,
            "created_at": "2026-01-06T12:00:00",
            "updated_at": "2026-01-06T14:00:00",
        }
        
        profile = UserProfile.from_firestore_dict(data)
        
        assert profile.uid == "test-uid"
        assert profile.email == "test@example.com"
        assert profile.display_name == "Test User"
        assert profile.onboarding_completed is True


class TestUserProfileUpdate:
    """Tests for UserProfileUpdate model."""

    def test_empty_update(self):
        """Test update with no fields."""
        update = UserProfileUpdate()
        assert update.display_name is None
        assert update.preferences is None

    def test_partial_update(self):
        """Test update with some fields."""
        update = UserProfileUpdate(display_name="New Name")
        assert update.display_name == "New Name"
        assert update.preferences is None


class TestUserPreferencesUpdate:
    """Tests for UserPreferencesUpdate model."""

    def test_timezone_only(self):
        """Test updating only timezone."""
        update = UserPreferencesUpdate(timezone="Europe/London")
        assert update.timezone == "Europe/London"
        assert update.typical_wake_time is None

    def test_multiple_fields(self):
        """Test updating multiple fields."""
        update = UserPreferencesUpdate(
            timezone="Asia/Tokyo",
            notifications_enabled=False,
        )
        assert update.timezone == "Asia/Tokyo"
        assert update.notifications_enabled is False


# -----------------------------------------------------------------------------
# Service Tests (with mocked repository)
# -----------------------------------------------------------------------------


class TestUserService:
    """Tests for UserService."""

    @pytest.fixture
    def mock_user(self):
        """Create a mock authenticated user."""
        return UserContext(
            uid="test-uid-123",
            email="test@example.com",
            email_verified=True,
            auth_time=datetime.utcnow(),
        )

    @pytest.fixture
    def mock_profile(self, mock_user):
        """Create a mock user profile."""
        return UserProfile.create_default(
            uid=mock_user.uid,
            email=mock_user.email,
        )

    @pytest.mark.asyncio
    async def test_get_profile_creates_on_first_access(self, mock_user, mock_profile):
        """Test that profile is created on first access."""
        from app.services.user_service import UserService

        with patch("app.services.user_service.UserRepository") as MockRepo:
            mock_repo = MockRepo.return_value
            mock_repo.get_or_create = AsyncMock(return_value=mock_profile)

            service = UserService()
            profile = await service.get_profile(user=mock_user)

            mock_repo.get_or_create.assert_called_once_with(
                uid=mock_user.uid,
                email=mock_user.email,
            )
            assert profile.uid == mock_user.uid

    @pytest.mark.asyncio
    async def test_update_profile(self, mock_user, mock_profile):
        """Test profile update."""
        from app.services.user_service import UserService

        updated_profile = mock_profile.model_copy(
            update={"display_name": "New Name"}
        )

        with patch("app.services.user_service.UserRepository") as MockRepo:
            mock_repo = MockRepo.return_value
            mock_repo.get_or_create = AsyncMock(return_value=mock_profile)
            mock_repo.update = AsyncMock(return_value=updated_profile)

            service = UserService()
            update = UserProfileUpdate(display_name="New Name")
            profile = await service.update_profile(user=mock_user, update=update)

            assert profile.display_name == "New Name"


# -----------------------------------------------------------------------------
# API Response Format Tests
# -----------------------------------------------------------------------------


class TestUserProfileResponse:
    """Tests for API response formatting."""

    def test_response_from_model(self):
        """Test response creation from model."""
        from app.api.v1.users import UserProfileResponse

        profile = UserProfile.create_default(
            uid="test-uid",
            email="test@example.com",
        )
        response = UserProfileResponse.from_model(profile)

        assert response.uid == "test-uid"
        assert response.email == "test@example.com"
        assert response.schema_version == 1
        assert response.created_at.endswith("Z")  # ISO 8601 UTC

    def test_preferences_serialization(self):
        """Test that preferences are properly serialized."""
        from app.api.v1.users import UserPreferencesResponse

        prefs = UserPreferences(
            timezone="America/Chicago",
            preferred_focus_block_lengths=[FocusBlockLength.SHORT, FocusBlockLength.LONG],
        )
        response = UserPreferencesResponse.from_model(prefs)

        assert response.timezone == "America/Chicago"
        assert response.preferred_focus_block_lengths == [25, 60]
        assert "monday" in response.preferred_working_days


# -----------------------------------------------------------------------------
# Enum Tests
# -----------------------------------------------------------------------------


class TestEnums:
    """Tests for enum types."""

    def test_day_of_week_values(self):
        """Test DayOfWeek enum values."""
        assert DayOfWeek.MONDAY.value == "monday"
        assert DayOfWeek.SUNDAY.value == "sunday"

    def test_focus_block_length_values(self):
        """Test FocusBlockLength enum values."""
        assert FocusBlockLength.SHORT.value == 25
        assert FocusBlockLength.MEDIUM.value == 45
        assert FocusBlockLength.LONG.value == 60
        assert FocusBlockLength.EXTENDED.value == 90

    def test_focus_block_from_int(self):
        """Test creating FocusBlockLength from int."""
        length = FocusBlockLength(45)
        assert length == FocusBlockLength.MEDIUM
