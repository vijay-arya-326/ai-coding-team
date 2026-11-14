import pytest
from pydantic import ValidationError

from app.db.migrations import SCHEMA
from app.main import ActivityUpdateRequest


def test_activity_update_rejects_empty_updates():
    with pytest.raises(ValidationError):
        ActivityUpdateRequest()


def test_activity_update_rejects_blank_details():
    with pytest.raises(ValidationError):
        ActivityUpdateRequest(detail="   ")


def test_activity_update_accepts_completion_and_actor():
    update = ActivityUpdateRequest(completed=True, updated_by="sub-agent")
    assert update.completed is True
    assert update.updated_by == "sub-agent"


def test_background_activity_schema_is_workspace_scoped():
    assert "workspace_id TEXT PRIMARY KEY" in SCHEMA["background_activity"]
