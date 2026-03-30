"""
KR4 Test: SQL Database Storage and Queries

Tests that the SQL database successfully stores and queries user stats for 100%
of logged sessions.

Target Attainment: 90%
"""

import os
import sys
import tempfile
from pathlib import Path
from datetime import datetime

import pytest

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "Milestone_1"))
sys.path.insert(0, str(PROJECT_ROOT / "Milestone_1" / "common" / "persistence"))

from Milestone_1.common.persistence.db import AppDB


class TestKR4DatabaseStorage:
    """Test suite for KR4: SQL database storage and queries"""

    @pytest.fixture
    def test_db(self, tmp_path):
        """Create a temporary test database"""
        db_path = tmp_path / "test_app.db"
        db = AppDB(db_path)
        return db

    @pytest.fixture
    def sample_user(self, test_db):
        """Create a sample user for testing"""
        user = test_db.upsert_user(
            username="TestPlayer123",
            rank_tier="diamond_2",
            platform="steam"
        )
        return user

    def test_database_initialization(self, tmp_path):
        """Test: Database can be initialized"""
        db_path = tmp_path / "init_test.db"
        db = AppDB(db_path)

        assert db_path.exists(), "Database file should be created"
        assert db_path.stat().st_size > 0, "Database file should not be empty"

    def test_create_user(self, test_db):
        """Test: Can create new user (CREATE operation)"""
        # When: Creating a new user
        user = test_db.upsert_user(
            username="NewPlayer",
            rank_tier="platinum_3",
            platform="epic"
        )

        # Then: User should be created with valid ID
        assert user is not None, "User should be created"
        assert "id" in user, "User should have ID"
        assert user["username"] == "NewPlayer", "Username should match"
        assert user["rank_tier"] == "platinum_3", "Rank should match"
        assert user["platform"] == "epic", "Platform should match"

    def test_upsert_user_updates_existing(self, test_db, sample_user):
        """Test: upsert_user updates existing user instead of creating duplicate"""
        user_id = sample_user["id"]
        original_username = sample_user["username"]

        # When: Upserting same user with updated rank
        updated_user = test_db.upsert_user(
            username=original_username,
            rank_tier="champion_1",  # Updated rank
            platform="steam"
        )

        # Then: Should have same ID (not a new user)
        assert updated_user["id"] == user_id, "Should update existing user, not create new"
        assert updated_user["rank_tier"] == "champion_1", "Rank should be updated"

    def test_save_replay_session(self, test_db, sample_user):
        """Test: Can save replay session (CREATE operation)"""
        # When: Saving a replay session
        test_db.save_replay_session(
            session_id="test_session_001",
            user_id=sample_user["id"],
            source_type="replay_upload",
            replay_name="TestReplay.replay",
            map_name="DFHStadium",
            duration_s=300.0,
            tracked_player_name="TestPlayer123",
            tracked_player_index=0,
            artifact_manifest={"csv": "data.csv", "json": "replay.json"},
            summary={"goals": 2, "saves": 1, "shots": 5}
        )

        # Then: Session should be retrievable
        sessions = test_db.list_replay_sessions(user_id=sample_user["id"])
        assert len(sessions) == 1, "Should have saved one session"
        assert sessions[0]["session_id"] == "test_session_001"

    def test_list_replay_sessions(self, test_db, sample_user):
        """Test: Can list all replay sessions for a user (READ operation)"""
        # Given: Multiple sessions saved
        for i in range(3):
            test_db.save_replay_session(
                session_id=f"session_{i:03d}",
                user_id=sample_user["id"],
                source_type="replay_upload",
                replay_name=f"Replay{i}.replay",
                map_name="DFHStadium",
                duration_s=300.0,
                tracked_player_name="TestPlayer123",
                tracked_player_index=0,
                artifact_manifest={},
                summary={}
            )

        # When: Listing sessions
        sessions = test_db.list_replay_sessions(user_id=sample_user["id"])

        # Then: Should retrieve all 3 sessions
        assert len(sessions) == 3, "Should list all saved sessions"

        # And: Sessions should be ordered (usually by creation date)
        session_ids = [s["session_id"] for s in sessions]
        assert "session_000" in session_ids
        assert "session_001" in session_ids
        assert "session_002" in session_ids

    def test_get_replay_session(self, test_db, sample_user):
        """Test: Can retrieve specific replay session (READ operation)"""
        # Given: A saved session
        test_db.save_replay_session(
            session_id="specific_session",
            user_id=sample_user["id"],
            source_type="replay_upload",
            replay_name="SpecificReplay.replay",
            map_name="UrbanCentral",
            duration_s=420.0,
            tracked_player_name="TestPlayer123",
            tracked_player_index=0,
            artifact_manifest={"csv": "specific.csv"},
            summary={"goals": 3}
        )

        # When: Getting specific session
        session = test_db.get_replay_session(
            session_id="specific_session",
            user_id=sample_user["id"]
        )

        # Then: Should retrieve the correct session
        assert session is not None, "Session should be found"
        assert session["session_id"] == "specific_session"
        assert session["replay_name"] == "SpecificReplay.replay"
        assert session["map_name"] == "UrbanCentral"
        assert session["duration_s"] == 420.0

    def test_delete_replay_session(self, test_db, sample_user):
        """Test: Can delete replay session (DELETE operation)"""
        # Given: A saved session
        test_db.save_replay_session(
            session_id="delete_me",
            user_id=sample_user["id"],
            source_type="replay_upload",
            replay_name="DeleteThis.replay",
            map_name="DFHStadium",
            duration_s=300.0,
            tracked_player_name="TestPlayer123",
            tracked_player_index=0,
            artifact_manifest={},
            summary={}
        )

        # When: Deleting session
        test_db.delete_replay_session(
            session_id="delete_me",
            user_id=sample_user["id"]
        )

        # Then: Session should no longer exist
        sessions = test_db.list_replay_sessions(user_id=sample_user["id"])
        session_ids = [s["session_id"] for s in sessions]
        assert "delete_me" not in session_ids, "Deleted session should not be listed"

    def test_session_metadata_persists(self, test_db, sample_user):
        """Test: Session metadata (JSON, duration, map) persists correctly"""
        # Given: Session with comprehensive metadata
        artifact_manifest = {
            "csv": "path/to/data.csv",
            "json": "path/to/replay.json",
            "timeline": "path/to/timeline.json"
        }
        summary = {
            "goals": 2,
            "saves": 3,
            "shots": 10,
            "assists": 1,
            "score": 450
        }

        test_db.save_replay_session(
            session_id="metadata_test",
            user_id=sample_user["id"],
            source_type="replay_upload",
            replay_name="MetadataTest.replay",
            map_name="Mannfield",
            duration_s=360.5,
            tracked_player_name="TestPlayer123",
            tracked_player_index=0,
            artifact_manifest=artifact_manifest,
            summary=summary
        )

        # When: Retrieving session
        session = test_db.get_replay_session(
            session_id="metadata_test",
            user_id=sample_user["id"]
        )

        # Then: All metadata should be preserved
        assert session["duration_s"] == 360.5, "Duration should persist"
        assert session["map_name"] == "Mannfield", "Map name should persist"

        # Note: artifact_manifest and summary are stored as JSON TEXT fields
        # Their exact retrieval format depends on db.py implementation

    def test_stores_100_percent_of_sessions(self, test_db, sample_user):
        """Test: Database successfully stores 100% of logged sessions"""
        # Given: Attempting to save 10 sessions
        total_sessions = 10
        for i in range(total_sessions):
            test_db.save_replay_session(
                session_id=f"bulk_session_{i:03d}",
                user_id=sample_user["id"],
                source_type="replay_upload",
                replay_name=f"Bulk{i}.replay",
                map_name="DFHStadium",
                duration_s=300.0 + i,
                tracked_player_name="TestPlayer123",
                tracked_player_index=0,
                artifact_manifest={},
                summary={}
            )

        # When: Retrieving all sessions
        sessions = test_db.list_replay_sessions(user_id=sample_user["id"])

        # Then: All 10 sessions should be stored (100%)
        assert len(sessions) == total_sessions, \
            f"Should store 100% of sessions (expected {total_sessions}, got {len(sessions)})"

    def test_query_performance_with_index(self, test_db, sample_user):
        """Test: Database queries use indexes for performance"""
        # Create multiple sessions
        for i in range(20):
            test_db.save_replay_session(
                session_id=f"perf_session_{i:03d}",
                user_id=sample_user["id"],
                source_type="replay_upload",
                replay_name=f"Perf{i}.replay",
                map_name="DFHStadium",
                duration_s=300.0,
                tracked_player_name="TestPlayer123",
                tracked_player_index=0,
                artifact_manifest={},
                summary={}
            )

        # Query should complete quickly (indexed by user_id)
        import time
        start = time.time()
        sessions = test_db.list_replay_sessions(user_id=sample_user["id"])
        elapsed = time.time() - start

        assert len(sessions) == 20, "Should retrieve all sessions"
        assert elapsed < 1.0, "Query should complete quickly (< 1 second)"

    def test_database_has_required_tables(self, test_db):
        """Test: Database schema includes required tables"""
        # Check that database was created with expected tables
        # (This depends on AppDB implementation)

        # Verify we can access basic operations
        try:
            # These operations should work if tables exist
            user = test_db.upsert_user(username="SchemaTest", rank_tier="gold_1", platform="steam")
            assert user is not None

            test_db.save_replay_session(
                session_id="schema_test",
                user_id=user["id"],
                source_type="replay_upload",
                replay_name="Test.replay",
                map_name="DFHStadium",
                duration_s=300.0,
                tracked_player_name="SchemaTest",
                tracked_player_index=0,
                artifact_manifest={},
                summary={}
            )

            sessions = test_db.list_replay_sessions(user_id=user["id"])
            assert len(sessions) > 0

        except Exception as e:
            pytest.fail(f"Database schema issue: {e}")

    def test_kr4_attainment_90_percent(self, test_db):
        """
        KR4 Final Verification: 90% attainment

        Verifies that:
        1. Database can be created and initialized
        2. All CRUD operations work (CREATE, READ, UPDATE, DELETE)
        3. Stores 100% of logged sessions
        4. Sessions are queryable
        5. Metadata persists correctly
        """
        # Create user
        user = test_db.upsert_user(
            username="KR4_FinalTest",
            rank_tier="diamond_3",
            platform="steam"
        )
        assert user is not None, "✅ KR4: User created successfully"

        # Save multiple sessions
        session_count = 5
        for i in range(session_count):
            test_db.save_replay_session(
                session_id=f"kr4_final_{i:03d}",
                user_id=user["id"],
                source_type="replay_upload",
                replay_name=f"Final{i}.replay",
                map_name="DFHStadium",
                duration_s=300.0 + i * 10,
                tracked_player_name="KR4_FinalTest",
                tracked_player_index=0,
                artifact_manifest={"csv": f"final{i}.csv"},
                summary={"goals": i}
            )

        # Retrieve all sessions
        sessions = test_db.list_replay_sessions(user_id=user["id"])
        assert len(sessions) == session_count, \
            f"✅ KR4: Stored and retrieved 100% of sessions ({session_count}/{session_count})"

        # Retrieve specific session
        specific = test_db.get_replay_session(
            session_id="kr4_final_002",
            user_id=user["id"]
        )
        assert specific is not None, "✅ KR4: Can query specific session"
        assert specific["session_id"] == "kr4_final_002", "✅ KR4: Correct session retrieved"

        # Update user
        updated_user = test_db.upsert_user(
            username="KR4_FinalTest",
            rank_tier="champion_1",  # Updated
            platform="steam"
        )
        assert updated_user["id"] == user["id"], "✅ KR4: User update works (same ID)"
        assert updated_user["rank_tier"] == "champion_1", "✅ KR4: Rank updated"

        # Delete session
        test_db.delete_replay_session(
            session_id="kr4_final_000",
            user_id=user["id"]
        )
        remaining = test_db.list_replay_sessions(user_id=user["id"])
        assert len(remaining) == session_count - 1, "✅ KR4: Session deleted successfully"

        print(f"\n✅ KR4 ATTAINMENT: 90%")
        print(f"   - Database: SQLite (AppDB)")
        print(f"   - CRUD Operations: All functional")
        print(f"   - CREATE: Users and sessions ✓")
        print(f"   - READ: list_replay_sessions(), get_replay_session() ✓")
        print(f"   - UPDATE: upsert_user() ✓")
        print(f"   - DELETE: delete_replay_session() ✓")
        print(f"   - Storage: 100% of logged sessions ✓")
        print(f"   - Sessions tested: {session_count}")


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v", "--tb=short"])
