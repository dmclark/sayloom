"""Durable authored target definitions and operation-specific safe errors."""

from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

from sqlalchemy import select

from local_text.database import ApplicationDatabase
from local_text.models import Target, TargetOperationError, utc_now
from local_text.targets import INITIAL_TARGETS, SendStrategy, TargetDefinition


class TargetNotFoundError(LookupError):
    pass


@dataclass(frozen=True)
class TargetRecord:
    id: str
    display_name: str
    application_name: str
    application_bundle_id: str
    icon: str
    send_strategy: SendStrategy
    enabled: bool
    created_at: datetime
    updated_at: datetime

    @property
    def definition(self) -> TargetDefinition:
        return TargetDefinition(
            display_name=self.display_name,
            application_name=self.application_name,
            application_bundle_id=self.application_bundle_id,
            icon=self.icon,
            send_strategy=self.send_strategy,
        )


@dataclass(frozen=True)
class OperationErrorRecord:
    operation: str
    code: str
    message: str
    retry_action: str
    occurred_at: datetime


def _record(target: Target) -> TargetRecord:
    return TargetRecord(
        id=target.id,
        display_name=target.display_name,
        application_name=target.application_name,
        application_bundle_id=target.application_bundle_id,
        icon=target.icon,
        send_strategy=SendStrategy(target.send_strategy),
        enabled=target.enabled,
        created_at=target.created_at,
        updated_at=target.updated_at,
    )


class TargetStore:
    def __init__(self, database: ApplicationDatabase) -> None:
        self.database = database

    def seed_defaults(self) -> int:
        created = 0
        with self.database.session_factory.begin() as session:
            for target_id, definition in INITIAL_TARGETS:
                if session.get(Target, target_id) is not None:
                    continue
                session.add(
                    Target(
                        id=target_id,
                        **definition.model_dump(mode="json"),
                        enabled=True,
                        created_at=utc_now(),
                        updated_at=utc_now(),
                    )
                )
                created += 1
        return created

    def list(self) -> list[TargetRecord]:
        with self.database.session_factory() as session:
            targets = session.scalars(select(Target).order_by(Target.created_at, Target.id)).all()
            return [_record(target) for target in targets]

    def get(self, target_id: str) -> TargetRecord:
        with self.database.session_factory() as session:
            target = session.get(Target, target_id)
            if target is None:
                raise TargetNotFoundError(target_id)
            return _record(target)

    def create(self, definition: TargetDefinition) -> TargetRecord:
        target_id = uuid4().hex
        now = utc_now()
        with self.database.session_factory.begin() as session:
            target = Target(
                id=target_id,
                **definition.model_dump(mode="json"),
                enabled=True,
                created_at=now,
                updated_at=now,
            )
            session.add(target)
            session.flush()
            return _record(target)

    def update(self, target_id: str, definition: TargetDefinition) -> TargetRecord:
        with self.database.session_factory.begin() as session:
            target = session.get(Target, target_id)
            if target is None:
                raise TargetNotFoundError(target_id)
            for name, value in definition.model_dump(mode="json").items():
                setattr(target, name, value)
            target.updated_at = utc_now()
            self._clear_error(session, target_id, "save")
            session.flush()
            return _record(target)

    def set_enabled(self, target_id: str, enabled: bool) -> TargetRecord:
        with self.database.session_factory.begin() as session:
            target = session.get(Target, target_id)
            if target is None:
                raise TargetNotFoundError(target_id)
            target.enabled = enabled
            target.updated_at = utc_now()
            self._clear_error(session, target_id, "disable" if not enabled else "enable")
            session.flush()
            return _record(target)

    def delete(self, target_id: str) -> None:
        with self.database.session_factory.begin() as session:
            target = session.get(Target, target_id)
            if target is None:
                raise TargetNotFoundError(target_id)
            session.delete(target)

    def errors(self, target_id: str) -> list[OperationErrorRecord]:
        with self.database.session_factory() as session:
            errors = session.scalars(
                select(TargetOperationError)
                .where(TargetOperationError.target_id == target_id)
                .order_by(TargetOperationError.occurred_at)
            ).all()
            return [
                OperationErrorRecord(
                    operation=error.operation,
                    code=error.code,
                    message=error.message,
                    retry_action=error.retry_action,
                    occurred_at=error.occurred_at,
                )
                for error in errors
            ]

    def record_error(
        self, target_id: str, operation: str, code: str, message: str, retry_action: str
    ) -> None:
        with self.database.session_factory.begin() as session:
            if session.get(Target, target_id) is None:
                raise TargetNotFoundError(target_id)
            error = session.get(TargetOperationError, (target_id, operation))
            if error is None:
                error = TargetOperationError(target_id=target_id, operation=operation)
                session.add(error)
            error.code = code
            error.message = message
            error.retry_action = retry_action
            error.occurred_at = utc_now()

    def clear_error(self, target_id: str, operation: str) -> None:
        with self.database.session_factory.begin() as session:
            self._clear_error(session, target_id, operation)

    @staticmethod
    def _clear_error(session: object, target_id: str, operation: str) -> None:
        error = session.get(TargetOperationError, (target_id, operation))
        if error is not None:
            session.delete(error)
