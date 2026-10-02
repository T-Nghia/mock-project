from enum import Enum

from app.models.user import UserRole


class Permission(str, Enum):
    READ_PROFILE = "profile:read"
    MANAGE_USERS = "users:manage"
    VIEW_USERS = "users:view"
    CREATE_TEACHER = "teachers:create"
    UPDATE_USER_ROLE = "users:update_role"
    UPDATE_USER_STATUS = "users:update_status"
    CREATE_DOCUMENT = "documents:create"
    REVIEW_DOCUMENT = "documents:review"
    READ_DOCUMENT = "documents:read"
    USE_CHAT = "chat:use"
    SOCIAL_INTERACT = "social:interact"


ROLE_PERMISSIONS: dict[UserRole, set[Permission]] = {
    UserRole.ADMIN: {
        Permission.READ_PROFILE,
        Permission.MANAGE_USERS,
        Permission.VIEW_USERS,
        Permission.CREATE_TEACHER,
        Permission.UPDATE_USER_ROLE,
        Permission.UPDATE_USER_STATUS,
        Permission.CREATE_DOCUMENT,
        Permission.REVIEW_DOCUMENT,
        Permission.READ_DOCUMENT,
        Permission.USE_CHAT,
        Permission.SOCIAL_INTERACT,
    },
    UserRole.TEACHER: {
        Permission.READ_PROFILE,
        Permission.CREATE_DOCUMENT,
        Permission.REVIEW_DOCUMENT,
        Permission.READ_DOCUMENT,
        Permission.USE_CHAT,
        Permission.SOCIAL_INTERACT,
    },
    UserRole.STUDENT: {
        Permission.READ_PROFILE,
        Permission.READ_DOCUMENT,
        Permission.USE_CHAT,
        Permission.SOCIAL_INTERACT,
    },
}


def normalize_role(role: UserRole | str) -> UserRole:
    if isinstance(role, UserRole):
        return role

    role_value = str(role).strip().lower()
    for item in UserRole:
        if role_value in {item.value, item.name.lower()}:
            return item

    raise ValueError(f"Unknown role: {role}")


def normalize_permission(permission: Permission | str) -> Permission:
    if isinstance(permission, Permission):
        return permission

    permission_value = str(permission).strip().lower()
    for item in Permission:
        if permission_value == item.value:
            return item

    raise ValueError(f"Unknown permission: {permission}")


def get_role_permissions(role: UserRole | str) -> set[Permission]:
    return set(ROLE_PERMISSIONS[normalize_role(role)])


def has_permission(role: UserRole | str, permission: Permission | str) -> bool:
    return normalize_permission(permission) in get_role_permissions(role)
