"""State-machine and human-only-guard tests.

Uses a fake session (the audit service only calls add/flush), so no DB is
needed. What matters here:
  * only legal transitions pass,
  * automation can NEVER move a case into certified or filed,
  * a human actor CAN.
"""

from __future__ import annotations

import uuid

import pytest

from app.core.constants import ALLOWED_TRANSITIONS, CaseStatus
from app.models.case import Case
from app.services.audit import TransitionError, transition


class FakeSession:
    def __init__(self):
        self.added = []

    def add(self, obj):
        self.added.append(obj)

    def flush(self):
        pass


def make_case(status: CaseStatus) -> Case:
    case = Case(
        firm_id=uuid.uuid4(),
        client_id=uuid.uuid4(),
        status=status.value,
    )
    case.id = uuid.uuid4()
    return case


class TestLegalTransitions:
    def test_intake_to_extracting(self):
        session, case = FakeSession(), make_case(CaseStatus.INTAKE)
        transition(session, case, CaseStatus.EXTRACTING)
        assert case.status == CaseStatus.EXTRACTING.value

    def test_pending_documents_loops_back_to_validating(self):
        session, case = FakeSession(), make_case(CaseStatus.PENDING_DOCUMENTS)
        transition(session, case, CaseStatus.VALIDATING)
        assert case.status == CaseStatus.VALIDATING.value

    def test_every_transition_writes_an_event(self):
        session, case = FakeSession(), make_case(CaseStatus.INTAKE)
        transition(session, case, CaseStatus.EXTRACTING)
        from app.models.case import CaseEvent

        events = [obj for obj in session.added if isinstance(obj, CaseEvent)]
        assert len(events) == 1
        assert events[0].old_status == CaseStatus.INTAKE.value
        assert events[0].new_status == CaseStatus.EXTRACTING.value


class TestIllegalTransitions:
    def test_cannot_skip_from_intake_to_ready(self):
        session, case = FakeSession(), make_case(CaseStatus.INTAKE)
        with pytest.raises(TransitionError, match="illegal transition"):
            transition(session, case, CaseStatus.READY_FOR_REVIEW)

    def test_filed_is_terminal(self):
        session, case = FakeSession(), make_case(CaseStatus.FILED)
        for target in CaseStatus:
            with pytest.raises(TransitionError):
                transition(session, case, target)

    def test_status_unchanged_after_rejected_transition(self):
        session, case = FakeSession(), make_case(CaseStatus.INTAKE)
        with pytest.raises(TransitionError):
            transition(session, case, CaseStatus.FILED)
        assert case.status == CaseStatus.INTAKE.value


class TestHumanOnlyGuard:
    """The §1 non-negotiable: automation never certifies or files."""

    def test_automation_cannot_certify(self):
        session, case = FakeSession(), make_case(CaseStatus.READY_FOR_REVIEW)
        with pytest.raises(TransitionError, match="requires a human actor"):
            transition(session, case, CaseStatus.CERTIFIED, by_automation=True)

    def test_automation_cannot_file(self):
        session, case = FakeSession(), make_case(CaseStatus.CERTIFIED)
        with pytest.raises(TransitionError, match="requires a human actor"):
            transition(session, case, CaseStatus.FILED, by_automation=True)

    def test_human_can_certify(self):
        session, case = FakeSession(), make_case(CaseStatus.READY_FOR_REVIEW)
        transition(
            session, case, CaseStatus.CERTIFIED,
            by_automation=False, actor_user_id=uuid.uuid4(),
        )
        assert case.status == CaseStatus.CERTIFIED.value

    def test_default_is_automation(self):
        """Omitting by_automation must be the SAFE direction (guard active)."""
        session, case = FakeSession(), make_case(CaseStatus.READY_FOR_REVIEW)
        with pytest.raises(TransitionError):
            transition(session, case, CaseStatus.CERTIFIED)


class TestStateMachineShape:
    def test_certified_only_reachable_from_ready_for_review(self):
        sources = [
            s for s, targets in ALLOWED_TRANSITIONS.items()
            if CaseStatus.CERTIFIED in targets
        ]
        assert sources == [CaseStatus.READY_FOR_REVIEW]

    def test_filed_only_reachable_from_certified(self):
        sources = [
            s for s, targets in ALLOWED_TRANSITIONS.items()
            if CaseStatus.FILED in targets
        ]
        assert sources == [CaseStatus.CERTIFIED]

    def test_every_status_has_a_transition_entry(self):
        assert set(ALLOWED_TRANSITIONS) == set(CaseStatus)
