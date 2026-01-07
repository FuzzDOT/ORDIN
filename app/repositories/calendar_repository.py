"""
Calendar Repository
===================
Firestore repository for calendar integrations and busy blocks.

COLLECTION STRUCTURE:
    Integration state: users/{uid}/integrations/calendar/google
    Busy blocks: users/{uid}/calendar_busy_blocks/{block_id}

The integration document stores OAuth tokens and sync metadata.
Busy blocks are privacy-preserving - no event titles stored.

IDEMPOTENT OPERATIONS:
- Busy blocks use deterministic IDs (hash of provider+calendar+event)
- Upsert semantics ensure idempotent sync operations
- Stale blocks (outside sync window or missing from source) are deleted

ASYNC SAFETY:
Firestore SDK operations are synchronous. This repository uses
asyncio.to_thread() to run them in a thread pool.
"""

import asyncio
from datetime import datetime
from typing import Optional

from google.cloud import firestore

from app.core.logging import get_logger
from app.db import FirestoreError, get_firestore_client
from app.models.calendar import (
    BusyBlock,
    CalendarIntegration,
    CalendarProvider,
    IntegrationStatus,
)

logger = get_logger(__name__)

# Firestore collection paths
USERS_COLLECTION = "users"
INTEGRATIONS_SUBCOLLECTION = "integrations"
CALENDAR_DOC = "calendar"
BUSY_BLOCKS_SUBCOLLECTION = "calendar_busy_blocks"


class CalendarRepositoryError(FirestoreError):
    """Base exception for calendar repository operations."""

    pass


class IntegrationNotFoundError(CalendarRepositoryError):
    """Raised when a calendar integration is not found."""

    pass


class CalendarRepository:
    """
    Repository for calendar integration and busy block Firestore operations.
    
    STRUCTURE:
    - Integration state: users/{uid}/integrations/calendar/{provider}
    - Busy blocks: users/{uid}/calendar_busy_blocks/{block_id}
    
    All methods are async-safe using asyncio.to_thread().
    
    Usage:
        repo = CalendarRepository()
        
        # Store integration
        await repo.save_integration(uid, integration)
        
        # Upsert busy blocks during sync
        await repo.upsert_busy_blocks(uid, blocks)
        
        # Get blocks for availability computation
        blocks = await repo.get_busy_blocks(uid, start, end)
    """

    def __init__(self) -> None:
        """Initialize the repository with Firestore client."""
        self._db = get_firestore_client()

    # =========================================================================
    # INTEGRATION STATE METHODS
    # =========================================================================

    def _get_integration_ref(self, uid: str, provider: CalendarProvider):
        """Get document reference for a calendar integration."""
        return (
            self._db.collection(USERS_COLLECTION)
            .document(uid)
            .collection(INTEGRATIONS_SUBCOLLECTION)
            .document(CALENDAR_DOC)
            .collection(provider.value)
            .document("state")
        )

    def _get_provider_collection_ref(self, uid: str):
        """Get the integrations/calendar collection reference."""
        return (
            self._db.collection(USERS_COLLECTION)
            .document(uid)
            .collection(INTEGRATIONS_SUBCOLLECTION)
            .document(CALENDAR_DOC)
        )

    async def get_integration(
        self,
        uid: str,
        provider: CalendarProvider,
    ) -> Optional[CalendarIntegration]:
        """
        Get calendar integration state for a user and provider.
        
        Args:
            uid: User's Firebase UID
            provider: Calendar provider (google, apple, microsoft)
        
        Returns:
            CalendarIntegration if exists, None otherwise
        """
        def _get():
            ref = self._get_integration_ref(uid, provider)
            doc = ref.get()
            if not doc.exists:
                return None
            return doc.to_dict()

        try:
            data = await asyncio.to_thread(_get)
            if data is None:
                return None
            
            # Convert Firestore timestamps to datetime
            if "connected_at" in data and data["connected_at"]:
                data["connected_at"] = data["connected_at"].isoformat() if hasattr(data["connected_at"], "isoformat") else data["connected_at"]
            if "last_sync_at" in data and data["last_sync_at"]:
                data["last_sync_at"] = data["last_sync_at"].isoformat() if hasattr(data["last_sync_at"], "isoformat") else data["last_sync_at"]
            if "token_expires_at" in data and data["token_expires_at"]:
                data["token_expires_at"] = data["token_expires_at"].isoformat() if hasattr(data["token_expires_at"], "isoformat") else data["token_expires_at"]
            
            return CalendarIntegration.model_validate(data)
            
        except Exception as e:
            logger.error(
                "get_integration_error",
                uid=uid,
                provider=provider.value,
                error=str(e),
            )
            raise CalendarRepositoryError(f"Failed to get integration: {e}")

    async def save_integration(
        self,
        uid: str,
        integration: CalendarIntegration,
    ) -> CalendarIntegration:
        """
        Save or update calendar integration state.
        
        Uses set with merge=False for full document replacement.
        
        Args:
            uid: User's Firebase UID
            integration: Integration state to save
        
        Returns:
            The saved integration
        """
        def _save():
            ref = self._get_integration_ref(uid, integration.provider)
            data = integration.model_dump(mode="json")
            # Convert datetime strings to Firestore timestamps
            for ts_field in ["connected_at", "last_sync_at", "token_expires_at"]:
                if data.get(ts_field):
                    data[ts_field] = datetime.fromisoformat(data[ts_field])
            ref.set(data)

        try:
            await asyncio.to_thread(_save)
            logger.info(
                "integration_saved",
                uid=uid,
                provider=integration.provider.value,
                status=integration.status.value,
            )
            return integration
            
        except Exception as e:
            logger.error(
                "save_integration_error",
                uid=uid,
                provider=integration.provider.value,
                error=str(e),
            )
            raise CalendarRepositoryError(f"Failed to save integration: {e}")

    async def update_integration(
        self,
        uid: str,
        provider: CalendarProvider,
        updates: dict,
    ) -> Optional[CalendarIntegration]:
        """
        Partially update an integration document.
        
        Args:
            uid: User's Firebase UID
            provider: Calendar provider
            updates: Fields to update
        
        Returns:
            Updated integration if exists
        """
        def _update():
            ref = self._get_integration_ref(uid, provider)
            # Convert datetime strings to Firestore timestamps
            for ts_field in ["connected_at", "last_sync_at", "token_expires_at"]:
                if ts_field in updates and updates[ts_field]:
                    if isinstance(updates[ts_field], str):
                        updates[ts_field] = datetime.fromisoformat(updates[ts_field])
            ref.update(updates)
            return ref.get().to_dict()

        try:
            data = await asyncio.to_thread(_update)
            if data is None:
                return None
            return CalendarIntegration.model_validate(data)
            
        except Exception as e:
            logger.error(
                "update_integration_error",
                uid=uid,
                provider=provider.value,
                error=str(e),
            )
            raise CalendarRepositoryError(f"Failed to update integration: {e}")

    async def delete_integration(
        self,
        uid: str,
        provider: CalendarProvider,
    ) -> bool:
        """
        Delete a calendar integration and all associated busy blocks.
        
        Args:
            uid: User's Firebase UID
            provider: Calendar provider to disconnect
        
        Returns:
            True if deleted successfully
        """
        def _delete():
            # Delete integration state
            ref = self._get_integration_ref(uid, provider)
            ref.delete()
            
            # Delete associated busy blocks
            blocks_ref = self._get_busy_blocks_collection(uid)
            query = blocks_ref.where("provider", "==", provider.value)
            docs = query.stream()
            batch = self._db.batch()
            count = 0
            for doc in docs:
                batch.delete(doc.reference)
                count += 1
                # Firestore batches limited to 500 operations
                if count >= 450:
                    batch.commit()
                    batch = self._db.batch()
                    count = 0
            if count > 0:
                batch.commit()

        try:
            await asyncio.to_thread(_delete)
            logger.info(
                "integration_deleted",
                uid=uid,
                provider=provider.value,
            )
            return True
            
        except Exception as e:
            logger.error(
                "delete_integration_error",
                uid=uid,
                provider=provider.value,
                error=str(e),
            )
            raise CalendarRepositoryError(f"Failed to delete integration: {e}")

    async def list_integrations(
        self,
        uid: str,
    ) -> list[CalendarIntegration]:
        """
        List all calendar integrations for a user.
        
        Args:
            uid: User's Firebase UID
        
        Returns:
            List of all connected calendar integrations
        """
        integrations = []
        for provider in CalendarProvider:
            integration = await self.get_integration(uid, provider)
            if integration:
                integrations.append(integration)
        return integrations

    # =========================================================================
    # BUSY BLOCKS METHODS
    # =========================================================================

    def _get_busy_blocks_collection(self, uid: str):
        """Get busy blocks subcollection reference for a user."""
        return (
            self._db.collection(USERS_COLLECTION)
            .document(uid)
            .collection(BUSY_BLOCKS_SUBCOLLECTION)
        )

    async def get_busy_blocks(
        self,
        uid: str,
        start_time: datetime,
        end_time: datetime,
        provider: Optional[CalendarProvider] = None,
    ) -> list[BusyBlock]:
        """
        Get busy blocks within a time range.
        
        Args:
            uid: User's Firebase UID
            start_time: Range start (inclusive)
            end_time: Range end (exclusive)
            provider: Optional filter by provider
        
        Returns:
            List of busy blocks overlapping the range
        """
        def _get():
            ref = self._get_busy_blocks_collection(uid)
            # Query blocks that overlap with the time range
            # A block overlaps if: block.start < end_time AND block.end > start_time
            query = ref.where("start_time", "<", end_time)
            if provider:
                query = query.where("provider", "==", provider.value)
            docs = query.stream()
            
            blocks = []
            for doc in docs:
                data = doc.to_dict()
                # Filter out blocks that end before our start
                block_end = data.get("end_time")
                if hasattr(block_end, "timestamp"):
                    block_end = datetime.fromtimestamp(block_end.timestamp())
                if block_end and block_end > start_time:
                    blocks.append(data)
            return blocks

        try:
            data_list = await asyncio.to_thread(_get)
            blocks = []
            for data in data_list:
                # Convert Firestore timestamps
                for ts_field in ["start_time", "end_time", "synced_at"]:
                    if ts_field in data and data[ts_field]:
                        if hasattr(data[ts_field], "isoformat"):
                            data[ts_field] = data[ts_field].isoformat()
                        elif hasattr(data[ts_field], "timestamp"):
                            data[ts_field] = datetime.fromtimestamp(
                                data[ts_field].timestamp()
                            ).isoformat()
                blocks.append(BusyBlock.model_validate(data))
            
            logger.debug(
                "busy_blocks_retrieved",
                uid=uid,
                count=len(blocks),
                start=start_time.isoformat(),
                end=end_time.isoformat(),
            )
            return blocks
            
        except Exception as e:
            logger.error(
                "get_busy_blocks_error",
                uid=uid,
                error=str(e),
            )
            raise CalendarRepositoryError(f"Failed to get busy blocks: {e}")

    async def upsert_busy_blocks(
        self,
        uid: str,
        blocks: list[BusyBlock],
    ) -> int:
        """
        Upsert busy blocks using deterministic block IDs.
        
        Uses batch writes for efficiency. Block IDs are deterministic
        hashes, so repeated syncs update existing blocks.
        
        Args:
            uid: User's Firebase UID
            blocks: List of busy blocks to upsert
        
        Returns:
            Number of blocks upserted
        """
        if not blocks:
            return 0

        def _upsert():
            ref = self._get_busy_blocks_collection(uid)
            batch = self._db.batch()
            count = 0
            
            for block in blocks:
                doc_ref = ref.document(block.block_id)
                data = block.model_dump(mode="json")
                # Convert datetime strings to Firestore timestamps
                for ts_field in ["start_time", "end_time", "synced_at"]:
                    if data.get(ts_field):
                        data[ts_field] = datetime.fromisoformat(data[ts_field])
                batch.set(doc_ref, data)
                count += 1
                
                # Firestore batches limited to 500 operations
                if count >= 450:
                    batch.commit()
                    batch = self._db.batch()
                    
            # Commit remaining
            if count % 450 != 0:
                batch.commit()
                
            return len(blocks)

        try:
            upserted = await asyncio.to_thread(_upsert)
            logger.info(
                "busy_blocks_upserted",
                uid=uid,
                count=upserted,
            )
            return upserted
            
        except Exception as e:
            logger.error(
                "upsert_busy_blocks_error",
                uid=uid,
                error=str(e),
            )
            raise CalendarRepositoryError(f"Failed to upsert busy blocks: {e}")

    async def delete_stale_blocks(
        self,
        uid: str,
        provider: CalendarProvider,
        calendar_id: str,
        valid_block_ids: set[str],
        start_time: datetime,
        end_time: datetime,
    ) -> int:
        """
        Delete busy blocks that are no longer in the source calendar.
        
        Finds blocks within the sync window for the given provider/calendar
        that are not in the valid_block_ids set, and deletes them.
        
        Args:
            uid: User's Firebase UID
            provider: Calendar provider
            calendar_id: Calendar ID within the provider
            valid_block_ids: Set of block IDs that should be kept
            start_time: Sync window start
            end_time: Sync window end
        
        Returns:
            Number of blocks deleted
        """
        def _delete_stale():
            ref = self._get_busy_blocks_collection(uid)
            # Query blocks for this provider/calendar in the window
            query = (
                ref.where("provider", "==", provider.value)
                .where("calendar_id", "==", calendar_id)
                .where("start_time", ">=", start_time)
                .where("start_time", "<", end_time)
            )
            docs = list(query.stream())
            
            # Find stale blocks
            batch = self._db.batch()
            deleted = 0
            for doc in docs:
                if doc.id not in valid_block_ids:
                    batch.delete(doc.reference)
                    deleted += 1
                    if deleted >= 450:
                        batch.commit()
                        batch = self._db.batch()
            
            if deleted % 450 != 0:
                batch.commit()
                
            return deleted

        try:
            deleted = await asyncio.to_thread(_delete_stale)
            if deleted > 0:
                logger.info(
                    "stale_blocks_deleted",
                    uid=uid,
                    provider=provider.value,
                    calendar_id=calendar_id,
                    count=deleted,
                )
            return deleted
            
        except Exception as e:
            logger.error(
                "delete_stale_blocks_error",
                uid=uid,
                error=str(e),
            )
            raise CalendarRepositoryError(f"Failed to delete stale blocks: {e}")

    async def delete_all_blocks(
        self,
        uid: str,
        provider: Optional[CalendarProvider] = None,
    ) -> int:
        """
        Delete all busy blocks for a user, optionally filtered by provider.
        
        Args:
            uid: User's Firebase UID
            provider: Optional filter by provider
        
        Returns:
            Number of blocks deleted
        """
        def _delete_all():
            ref = self._get_busy_blocks_collection(uid)
            if provider:
                query = ref.where("provider", "==", provider.value)
            else:
                query = ref
                
            docs = list(query.stream())
            batch = self._db.batch()
            count = 0
            
            for doc in docs:
                batch.delete(doc.reference)
                count += 1
                if count >= 450:
                    batch.commit()
                    batch = self._db.batch()
                    count = 0
                    
            if count > 0:
                batch.commit()
                
            return len(docs)

        try:
            deleted = await asyncio.to_thread(_delete_all)
            logger.info(
                "all_blocks_deleted",
                uid=uid,
                provider=provider.value if provider else "all",
                count=deleted,
            )
            return deleted
            
        except Exception as e:
            logger.error(
                "delete_all_blocks_error",
                uid=uid,
                error=str(e),
            )
            raise CalendarRepositoryError(f"Failed to delete blocks: {e}")


# Global repository instance (singleton pattern)
_calendar_repository: Optional[CalendarRepository] = None


def get_calendar_repository() -> CalendarRepository:
    """Get the global CalendarRepository instance."""
    global _calendar_repository
    if _calendar_repository is None:
        _calendar_repository = CalendarRepository()
    return _calendar_repository
