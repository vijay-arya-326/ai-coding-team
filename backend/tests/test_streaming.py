from app.main import _is_user_facing_model_event


def test_streaming_excludes_planner_model_events():
    assert not _is_user_facing_model_event({"metadata": {"langgraph_node": "planner"}})


def test_streaming_includes_user_facing_model_events():
    assert _is_user_facing_model_event({"metadata": {"langgraph_node": "agent"}})
    assert _is_user_facing_model_event({"metadata": {"langgraph_node": "responder"}})
