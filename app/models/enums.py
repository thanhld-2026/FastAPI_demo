"""Các Enum dùng chung cho model (DB) và schema (API)."""

from enum import StrEnum


class UserRole(StrEnum):
    ADMIN = "admin"
    MEMBER = "member"


class TaskStatus(StrEnum):
    TODO = "TODO"
    IN_PROGRESS = "IN_PROGRESS"
    IN_REVIEW = "IN_REVIEW"
    DONE = "DONE"


class TaskPriority(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    URGENT = "URGENT"


class ProjectStatus(StrEnum):
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"  # task / comment trong project chỉ còn đọc được


class ActivityAction(StrEnum):
    CREATED = "created"
    UPDATED = "updated"
    ASSIGNED = "assigned"
    COMMENTED = "commented"
