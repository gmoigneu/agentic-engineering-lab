from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from agentic_lab.api.app import _queue_check_run
from agentic_lab.db.base import Base
from agentic_lab.domain.enums import AgentRole, RunSource


def test_failed_check_routes_to_ci() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(engine, expire_on_commit=False)
    with sessions.begin() as session:
        run, reason = _queue_check_run(
            session,
            {
                "check_run": {
                    "id": 99,
                    "conclusion": "failure",
                    "head_sha": "a" * 40,
                    "pull_requests": [{"number": 1}],
                }
            },
            123,
            RunSource.WEBHOOK,
        )
        assert reason is None
        assert run is not None
        assert run.role is AgentRole.CI
        assert run.check_run_id == 99
