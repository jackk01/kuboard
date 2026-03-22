from __future__ import annotations

from dataclasses import dataclass

from django.db.models import Case, IntegerField, Q, Value, When

from apps.clusters.models import Cluster
from apps.iam.models import User

from .models import SubjectMapping


@dataclass
class ImpersonationContext:
    username: str
    groups: list[str]
    mapping_ids: list[int]


def _mapping_identifier_priority(user: User) -> list[str]:
    identifiers = [user.email, str(user.id), user.username]
    return [item for item in identifiers if item]


def _unique_list(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        normalized = value.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def _unique_int_list(values: list[int]) -> list[int]:
    seen = set()
    result = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def resolve_impersonation_context(user: User, cluster: Cluster) -> ImpersonationContext:
    identifiers = _mapping_identifier_priority(user)
    memberships = list(user.group_memberships.select_related("group"))
    group_identifiers = []
    for membership in memberships:
        if membership.group.slug:
            group_identifiers.append(membership.group.slug)
        group_identifiers.append(membership.group.name)

    scoped_first = Case(
        When(cluster=cluster, then=Value(0)),
        default=Value(1),
        output_field=IntegerField(),
    )

    user_mapping = (
        SubjectMapping.objects.filter(
            source_type="user",
            source_identifier__in=identifiers,
            is_enabled=True,
        )
        .filter(Q(cluster=cluster) | Q(cluster__isnull=True))
        .annotate(scope_rank=scoped_first)
        .order_by("scope_rank", "id")
        .first()
    )

    group_mappings = list(
        SubjectMapping.objects.filter(
            source_type="group",
            source_identifier__in=group_identifiers,
            is_enabled=True,
        )
        .filter(Q(cluster=cluster) | Q(cluster__isnull=True))
        .annotate(scope_rank=scoped_first)
        .order_by("scope_rank", "id")
    )

    default_groups = ["kuboard:authenticated"]
    if user.is_staff:
        default_groups.append("kuboard:staff")
    if user.is_superuser:
        default_groups.append("kuboard:superuser")

    mapped_groups = []
    mapping_ids: list[int] = []

    if user_mapping:
        mapped_groups.extend(user_mapping.kubernetes_groups or [])
        mapping_ids.append(user_mapping.id)

    for mapping in group_mappings:
        mapped_groups.extend(mapping.kubernetes_groups or [])
        mapping_ids.append(mapping.id)

    username = user_mapping.kubernetes_username if user_mapping and user_mapping.kubernetes_username else user.email
    groups = _unique_list(default_groups + mapped_groups)
    return ImpersonationContext(username=username, groups=groups, mapping_ids=_unique_int_list(mapping_ids))
