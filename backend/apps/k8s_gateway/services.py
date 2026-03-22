from __future__ import annotations

import base64
import json
import os
import re
import shutil
import ssl
import subprocess
import tempfile
import time
from copy import deepcopy
from contextlib import ExitStack
from dataclasses import dataclass
from typing import Any
from urllib import error, parse, request

import yaml
from django.utils import timezone

from apps.clusters.models import Cluster, ClusterHealthState, ClusterStatus
from apps.rbac_bridge.services import ImpersonationContext, resolve_impersonation_context


class KubernetesAPIError(Exception):
    def __init__(self, message: str, *, status_code: int = 0, details: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.details = details


@dataclass
class ResourceDescriptor:
    group: str
    version: str
    name: str
    kind: str
    namespaced: bool
    verbs: list[str]
    short_names: list[str]


def build_resource_path(
    *,
    group: str,
    version: str,
    resource: str,
    namespaced: bool,
    namespace: str | None = None,
    name: str | None = None,
) -> str:
    if group in ("", "core"):
        prefix = f"/api/{version}"
    else:
        prefix = f"/apis/{group}/{version}"

    if namespaced:
        target_namespace = namespace or "default"
        path = f"{prefix}/namespaces/{parse.quote(target_namespace)}/{resource}"
        if name:
            return f"{path}/{parse.quote(name)}"
        return path

    path = f"{prefix}/{resource}"
    if name:
        return f"{path}/{parse.quote(name)}"
    return path


class KubernetesClient:
    LOG_TIMESTAMP_RE = re.compile(r"^(?P<timestamp>\S+)\s")

    def __init__(self, cluster: Cluster, actor=None):
        self.cluster = cluster
        self.actor = actor
        self.capability = cluster.capability
        self.credential = cluster.credential
        self.kubeconfig = yaml.safe_load(self.credential.get_kubeconfig())
        self.context_name = self.credential.active_context or self.kubeconfig.get("current-context")
        self.context_entry = self._find_named_entry("contexts", self.context_name)
        self.context_data = self.context_entry.get("context") or {}
        self.cluster_entry = self._find_named_entry("clusters", self.context_data.get("cluster"))
        self.user_entry = self._find_named_entry("users", self.context_data.get("user"))
        self.cluster_data = self.cluster_entry.get("cluster") or {}
        self.user_data = self.user_entry.get("user") or {}
        self.server = self.cluster_data.get("server", "").rstrip("/")
        self.default_namespace = self.context_data.get("namespace") or "default"
        self.impersonation: ImpersonationContext | None = None
        if (
            actor is not None
            and getattr(actor, "is_authenticated", False)
            and self.capability.supports_impersonation
        ):
            self.impersonation = resolve_impersonation_context(actor, cluster)

    def _find_named_entry(self, key: str, name: str | None) -> dict[str, Any]:
        for item in self.kubeconfig.get(key) or []:
            if item.get("name") == name:
                return item
        raise KubernetesAPIError(f"kubeconfig 中未找到 {key}:{name}", status_code=400)

    def _build_headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        token = self.user_data.get("token")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        else:
            username = self.user_data.get("username")
            password = self.user_data.get("password")
            if username and password:
                encoded = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("utf-8")
                headers["Authorization"] = f"Basic {encoded}"
            elif not (self.user_data.get("client-certificate-data") and self.user_data.get("client-key-data")):
                raise KubernetesAPIError(
                    "当前版本仅支持 token、username/password 或客户端证书认证的 kubeconfig。",
                    status_code=400,
                )

        if self.impersonation:
            headers["Impersonate-User"] = self.impersonation.username
        return headers

    def _apply_headers(self, req: request.Request, headers: dict[str, str]):
        for key, value in headers.items():
            req.add_header(key, value)
        if self.impersonation:
            for group in self.impersonation.groups:
                req.add_header("Impersonate-Group", group)

    def _build_ssl_context(self, stack: ExitStack) -> ssl.SSLContext:
        context = ssl.create_default_context()

        ca_data = self.cluster_data.get("certificate-authority-data")
        if ca_data:
            decoded = base64.b64decode(ca_data).decode("utf-8")
            context.load_verify_locations(cadata=decoded)

        cert_data = self.user_data.get("client-certificate-data")
        key_data = self.user_data.get("client-key-data")
        if cert_data and key_data:
            cert_file = stack.enter_context(tempfile.NamedTemporaryFile(mode="wb", delete=False))
            key_file = stack.enter_context(tempfile.NamedTemporaryFile(mode="wb", delete=False))
            cert_file.write(base64.b64decode(cert_data))
            key_file.write(base64.b64decode(key_data))
            cert_file.flush()
            key_file.flush()
            context.load_cert_chain(certfile=cert_file.name, keyfile=key_file.name)
            stack.callback(self._safe_remove, cert_file.name)
            stack.callback(self._safe_remove, key_file.name)

        return context

    @staticmethod
    def _safe_remove(path: str):
        try:
            os.remove(path)
        except FileNotFoundError:
            pass

    def _request(
        self,
        path: str,
        *,
        query: dict[str, Any] | None = None,
        method: str = "GET",
        body: bytes | None = None,
        content_type: str | None = None,
        accept: str = "application/json",
        expect_json: bool = True,
    ) -> Any:
        query_string = ""
        if query:
            filtered = {key: value for key, value in query.items() if value not in (None, "", [])}
            if filtered:
                query_string = "?" + parse.urlencode(filtered, doseq=True)

        url = f"{self.server}{path}{query_string}"
        headers = self._build_headers()
        headers["Accept"] = accept
        if content_type:
            headers["Content-Type"] = content_type

        with ExitStack() as stack:
            ssl_context = self._build_ssl_context(stack)
            opener = request.build_opener(request.HTTPSHandler(context=ssl_context))
            req = request.Request(url, method=method, data=body)
            self._apply_headers(req, headers)

            try:
                with opener.open(req, timeout=10) as response:
                    payload = response.read().decode("utf-8")
                    if not payload:
                        return {} if expect_json else ""
                    if expect_json:
                        return json.loads(payload)
                    return payload
            except error.HTTPError as exc:
                response_body = exc.read().decode("utf-8", errors="replace")
                try:
                    details = json.loads(response_body)
                    message = details.get("message") or details.get("error") or str(exc)
                except json.JSONDecodeError:
                    details = {"raw": response_body}
                    message = response_body or str(exc)
                raise KubernetesAPIError(message, status_code=exc.code, details=details) from exc
            except error.URLError as exc:
                raise KubernetesAPIError(
                    f"连接集群失败: {exc.reason}",
                    status_code=502,
                    details={"reason": str(exc.reason)},
                ) from exc

    def request_json(
        self,
        path: str,
        *,
        query: dict[str, Any] | None = None,
        method: str = "GET",
        body: bytes | None = None,
        content_type: str | None = None,
        accept: str = "application/json",
    ) -> dict[str, Any]:
        return self._request(
            path,
            query=query,
            method=method,
            body=body,
            content_type=content_type,
            accept=accept,
            expect_json=True,
        )

    def request_text(
        self,
        path: str,
        *,
        query: dict[str, Any] | None = None,
        method: str = "GET",
        body: bytes | None = None,
        content_type: str | None = None,
        accept: str = "text/plain, application/json",
    ) -> str:
        return self._request(
            path,
            query=query,
            method=method,
            body=body,
            content_type=content_type,
            accept=accept,
            expect_json=False,
        )

    def request_json_lines(
        self,
        path: str,
        *,
        query: dict[str, Any] | None = None,
        method: str = "GET",
        body: bytes | None = None,
        content_type: str | None = None,
        accept: str = "application/json",
        timeout: int = 20,
    ) -> list[dict[str, Any]]:
        query_string = ""
        if query:
            filtered = {key: value for key, value in query.items() if value not in (None, "", [])}
            if filtered:
                query_string = "?" + parse.urlencode(filtered, doseq=True)

        url = f"{self.server}{path}{query_string}"
        headers = self._build_headers()
        headers["Accept"] = accept
        if content_type:
            headers["Content-Type"] = content_type

        with ExitStack() as stack:
            ssl_context = self._build_ssl_context(stack)
            opener = request.build_opener(request.HTTPSHandler(context=ssl_context))
            req = request.Request(url, method=method, data=body)
            self._apply_headers(req, headers)

            try:
                with opener.open(req, timeout=timeout) as response:
                    events = []
                    for raw_line in response:
                        line = raw_line.decode("utf-8").strip()
                        if not line:
                            continue
                        try:
                            events.append(json.loads(line))
                        except json.JSONDecodeError as exc:
                            raise KubernetesAPIError(
                                "解析 watch 事件失败。",
                                status_code=502,
                                details={"raw": line},
                            ) from exc
                    return events
            except error.HTTPError as exc:
                response_body = exc.read().decode("utf-8", errors="replace")
                try:
                    details = json.loads(response_body)
                    message = details.get("message") or details.get("error") or str(exc)
                except json.JSONDecodeError:
                    details = {"raw": response_body}
                    message = response_body or str(exc)
                raise KubernetesAPIError(message, status_code=exc.code, details=details) from exc
            except error.URLError as exc:
                raise KubernetesAPIError(
                    f"连接集群失败: {exc.reason}",
                    status_code=502,
                    details={"reason": str(exc.reason)},
                ) from exc

    def probe(self) -> dict[str, Any]:
        started_at = time.monotonic()
        version = self.request_json("/version")
        latency_ms = int((time.monotonic() - started_at) * 1000)
        return {
            "version": version,
            "latency_ms": latency_ms,
        }

    def discover(self) -> dict[str, Any]:
        version = self.request_json("/version")
        core_versions = self.request_json("/api")
        api_groups = self.request_json("/apis")

        groups = []
        resource_index = {}
        supports_exec = False

        for core_version in core_versions.get("versions", []):
            resource_list = self.request_json(f"/api/{core_version}")
            supports_exec = supports_exec or any(
                item.get("name") == "pods/exec"
                for item in resource_list.get("resources", [])
            )
            resources = self._normalize_resources("", core_version, resource_list)
            groups.append(
                {
                    "group": "core",
                    "version": core_version,
                    "preferred_version": core_version,
                    "resources": resources,
                }
            )
            self._populate_resource_index(resource_index, resources)

        for group_entry in api_groups.get("groups", []):
            preferred = (group_entry.get("preferredVersion") or {}).get("version")
            if not preferred:
                continue
            group_name = group_entry.get("name", "")
            resource_list = self.request_json(f"/apis/{group_name}/{preferred}")
            resources = self._normalize_resources(group_name, preferred, resource_list)
            groups.append(
                {
                    "group": group_name,
                    "version": preferred,
                    "preferred_version": preferred,
                    "resources": resources,
                }
            )
            self._populate_resource_index(resource_index, resources)

        namespaces = []
        try:
            namespace_payload = self.request_json("/api/v1/namespaces", query={"limit": 200})
            namespaces = [
                {
                    "name": item["metadata"]["name"],
                    "phase": (item.get("status") or {}).get("phase", ""),
                }
                for item in namespace_payload.get("items", [])
            ]
        except KubernetesAPIError:
            namespaces = []

        return {
            "version": version,
            "context": {
                "name": self.context_name,
                "server": self.server,
                "default_namespace": self.default_namespace,
            },
            "groups": groups,
            "namespaces": namespaces,
            "resource_index": resource_index,
            "supports_exec": supports_exec,
        }

    def _normalize_resources(self, group: str, version: str, resource_list: dict[str, Any]) -> list[dict[str, Any]]:
        resources = []
        for item in resource_list.get("resources", []):
            name = item.get("name", "")
            if "/" in name:
                continue
            resources.append(
                {
                    "group": group or "core",
                    "version": version,
                    "name": name,
                    "kind": item.get("kind", ""),
                    "singular_name": item.get("singularName", ""),
                    "short_names": item.get("shortNames", []),
                    "namespaced": bool(item.get("namespaced")),
                    "verbs": item.get("verbs", []),
                }
            )
        resources.sort(key=lambda item: item["name"])
        return resources

    def _populate_resource_index(self, index: dict[str, Any], resources: list[dict[str, Any]]):
        for item in resources:
            key = self._resource_key(item["group"], item["version"], item["name"])
            index[key] = item

    @staticmethod
    def _resource_key(group: str, version: str, resource: str) -> str:
        return f"{group or 'core'}::{version}::{resource}"

    def _post_authorization_review(
        self,
        *,
        resource_name: str,
        review_kind: str,
        spec: dict[str, Any],
    ) -> dict[str, Any]:
        errors: list[dict[str, Any]] = []

        for version in ("v1", "v1beta1"):
            payload = {
                "apiVersion": f"authorization.k8s.io/{version}",
                "kind": review_kind,
                "spec": spec,
            }
            try:
                return self.request_json(
                    f"/apis/authorization.k8s.io/{version}/{resource_name}",
                    method="POST",
                    body=json.dumps(payload).encode("utf-8"),
                    content_type="application/json",
                )
            except KubernetesAPIError as exc:
                if exc.status_code not in (404, 405, 406):
                    raise
                errors.append(
                    {
                        "version": version,
                        "status_code": exc.status_code,
                        "message": str(exc),
                    }
                )

        raise KubernetesAPIError(
            "集群不支持 authorization.k8s.io 自审接口。",
            status_code=501,
            details={"candidates": errors},
        )

    def _run_self_subject_access_review(
        self,
        *,
        verb: str,
        group: str,
        version: str,
        resource: str,
        namespace: str | None = None,
        name: str | None = None,
        subresource: str | None = None,
    ) -> dict[str, Any]:
        resource_attributes = {
            "verb": verb,
            "group": group,
            "version": version,
            "resource": resource,
        }
        if namespace:
            resource_attributes["namespace"] = namespace
        if name:
            resource_attributes["name"] = name
        if subresource:
            resource_attributes["subresource"] = subresource

        review = self._post_authorization_review(
            resource_name="selfsubjectaccessreviews",
            review_kind="SelfSubjectAccessReview",
            spec={"resourceAttributes": resource_attributes},
        )
        status = review.get("status") or {}
        return {
            "allowed": bool(status.get("allowed")),
            "denied": bool(status.get("denied")),
            "reason": status.get("reason", ""),
            "evaluation_error": status.get("evaluationError", ""),
        }

    def get_self_subject_rules(self, namespace: str | None = None) -> dict[str, Any]:
        spec = {}
        if namespace:
            spec["namespace"] = namespace

        review = self._post_authorization_review(
            resource_name="selfsubjectrulesreviews",
            review_kind="SelfSubjectRulesReview",
            spec=spec,
        )
        status = review.get("status") or {}
        return {
            "namespace": namespace or "",
            "incomplete": bool(status.get("incomplete")),
            "evaluation_error": status.get("evaluationError", ""),
            "resource_rules": status.get("resourceRules", []),
            "non_resource_rules": status.get("nonResourceRules", []),
        }

    def get_resource_descriptor(self, group: str, version: str, resource: str) -> ResourceDescriptor:
        key = self._resource_key(group, version, resource)
        resource_index = self.capability.openapi_index or {}
        descriptor = resource_index.get(key)
        if descriptor is None:
            discovery = self.discover()
            resource_index = discovery["resource_index"]
            self.sync_capability_from_discovery(discovery)
            descriptor = resource_index.get(key)

        if descriptor is None:
            raise KubernetesAPIError("目标资源未在集群 discovery 中找到。", status_code=404)

        return ResourceDescriptor(
            group=group,
            version=version,
            name=resource,
            kind=descriptor.get("kind", ""),
            namespaced=bool(descriptor.get("namespaced")),
            verbs=descriptor.get("verbs", []),
            short_names=descriptor.get("short_names", []),
        )

    def _find_crd_schema(self, *, group: str, version: str, resource: str) -> dict[str, Any] | None:
        if not group:
            return None

        try:
            payload = self.request_json(
                f"/apis/apiextensions.k8s.io/v1/customresourcedefinitions/{resource}.{group}"
            )
        except KubernetesAPIError as exc:
            if exc.status_code == 404:
                return None
            raise

        spec = payload.get("spec") or {}
        versions = spec.get("versions") or []
        matched_version = next((item for item in versions if item.get("name") == version), None)
        if not matched_version:
            return None

        schema = ((matched_version.get("schema") or {}).get("openAPIV3Schema")) or {}
        return {
            "source": "crd",
            "schema_name": f"{group}/{version}/{spec.get('names', {}).get('kind', resource)}",
            "schema": schema,
            "additional_printer_columns": matched_version.get("additionalPrinterColumns", []),
            "subresources": matched_version.get("subresources", {}),
            "scope": spec.get("scope", ""),
        }

    def _load_openapi_v3_document(self, *, group: str, version: str) -> dict[str, Any]:
        index_payload = self.request_json("/openapi/v3")
        path_key = f"api/{version}" if not group else f"apis/{group}/{version}"
        document_info = (index_payload.get("paths") or {}).get(path_key)
        if not document_info:
            raise KubernetesAPIError(
                "集群未暴露目标 group/version 的 OpenAPI v3 文档。",
                status_code=404,
                details={"path_key": path_key},
            )

        server_relative_url = document_info.get("serverRelativeURL")
        if not server_relative_url:
            raise KubernetesAPIError(
                "OpenAPI v3 文档索引缺少 serverRelativeURL。",
                status_code=502,
                details={"path_key": path_key},
            )
        return self.request_json(server_relative_url)

    @staticmethod
    def _select_openapi_schema_name(
        schemas: dict[str, Any],
        *,
        kind: str,
        group: str,
        version: str,
    ) -> str | None:
        if not schemas:
            return None

        candidates = [name for name in schemas if name.endswith(f".{kind}")]
        if not candidates:
            candidates = [name for name in schemas if name.split(".")[-1] == kind]
        if not candidates:
            return None

        group_hint = group.split(".")[0] if group else "core"

        def score(name: str) -> tuple[int, int, int, int]:
            return (
                1 if f".{version}." in name else 0,
                1 if group and group_hint in name else 0,
                1 if not group and ".core." in name else 0,
                -len(name),
            )

        return sorted(candidates, key=score, reverse=True)[0]

    @staticmethod
    def _strip_openapi_extensions(schema: Any) -> Any:
        if isinstance(schema, dict):
            return {
                key: KubernetesClient._strip_openapi_extensions(value)
                for key, value in schema.items()
                if not str(key).startswith("x-kubernetes-")
            }
        if isinstance(schema, list):
            return [KubernetesClient._strip_openapi_extensions(item) for item in schema]
        return schema

    def _find_openapi_schema(self, *, group: str, version: str, kind: str) -> dict[str, Any] | None:
        try:
            document = self._load_openapi_v3_document(group=group, version=version)
        except KubernetesAPIError as exc:
            if exc.status_code == 404:
                return None
            raise

        schemas = (document.get("components") or {}).get("schemas") or {}
        schema_name = self._select_openapi_schema_name(schemas, kind=kind, group=group, version=version)
        if not schema_name:
            return None

        schema = deepcopy(schemas.get(schema_name) or {})
        return {
            "source": "openapi-v3",
            "schema_name": schema_name,
            "schema": self._strip_openapi_extensions(schema),
        }

    @classmethod
    def _infer_schema_from_value(cls, value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return {
                "type": "object",
                "properties": {key: cls._infer_schema_from_value(item) for key, item in value.items()},
            }
        if isinstance(value, list):
            item_schema = cls._infer_schema_from_value(value[0]) if value else {}
            return {
                "type": "array",
                "items": item_schema,
            }
        if isinstance(value, bool):
            return {"type": "boolean"}
        if isinstance(value, int):
            return {"type": "integer"}
        if isinstance(value, float):
            return {"type": "number"}
        if value is None:
            return {"type": "null"}
        return {"type": "string"}

    def _build_inferred_schema(self, *, group: str, version: str, resource: str, descriptor: ResourceDescriptor) -> dict[str, Any]:
        try:
            sample = self.list_resources(group=group, version=version, resource=resource, limit=1)
        except KubernetesAPIError:
            sample = None

        object_schema = self._infer_schema_from_value((sample or {}).get("items", [{}])[0] if sample else {})
        return {
            "source": "inferred",
            "schema_name": descriptor.kind or resource,
            "schema": object_schema,
            "sample_count": (sample or {}).get("metadata", {}).get("count", 0),
        }

    def get_resource_schema(self, *, group: str, version: str, resource: str) -> dict[str, Any]:
        descriptor = self.get_resource_descriptor(group, version, resource)
        resolved = (
            self._find_crd_schema(group=group, version=version, resource=resource)
            or self._find_openapi_schema(group=group, version=version, kind=descriptor.kind)
            or self._build_inferred_schema(group=group, version=version, resource=resource, descriptor=descriptor)
        )

        return {
            "resource": {
                "group": group or "core",
                "version": version,
                "name": resource,
                "kind": descriptor.kind,
                "namespaced": descriptor.namespaced,
                "verbs": descriptor.verbs,
                "short_names": descriptor.short_names,
            },
            "schema": resolved.get("schema") or {},
            "schema_name": resolved.get("schema_name", ""),
            "source": resolved["source"],
            "metadata": {
                key: value
                for key, value in resolved.items()
                if key not in {"schema", "schema_name", "source"}
            },
        }

    def check_resource_permissions(
        self,
        *,
        group: str,
        version: str,
        resource: str,
        namespace: str | None = None,
        name: str | None = None,
    ) -> dict[str, Any]:
        descriptor = self.get_resource_descriptor(group, version, resource)
        namespace_to_use = namespace or (self.default_namespace if descriptor.namespaced else None)
        verbs = {}

        for verb in ("get", "list", "watch", "create", "update", "patch", "delete"):
            review = self._run_self_subject_access_review(
                verb=verb,
                group=group,
                version=version,
                resource=resource,
                namespace=namespace_to_use if descriptor.namespaced else None,
                name=name if verb not in ("list", "create") else None,
            )
            verbs[verb] = review

        subresources = {}
        if (group or "core") == "core" and resource == "pods":
            subresources["log"] = self._run_self_subject_access_review(
                verb="get",
                group="",
                version="v1",
                resource="pods",
                namespace=namespace_to_use,
                name=name,
                subresource="log",
            )
            if self.capability.supports_exec:
                subresources["exec"] = self._run_self_subject_access_review(
                    verb="create",
                    group="",
                    version="v1",
                    resource="pods",
                    namespace=namespace_to_use,
                    name=name,
                    subresource="exec",
                )

        return {
            "resource": {
                "group": group or "core",
                "version": version,
                "name": resource,
                "kind": descriptor.kind,
                "namespaced": descriptor.namespaced,
            },
            "scope": {
                "namespace": namespace_to_use if descriptor.namespaced else None,
                "name": name or "",
            },
            "verbs": verbs,
            "subresources": subresources,
        }

    def list_resources(
        self,
        *,
        group: str,
        version: str,
        resource: str,
        namespace: str | None = None,
        limit: int = 100,
        continue_token: str | None = None,
    ) -> dict[str, Any]:
        descriptor = self.get_resource_descriptor(group, version, resource)
        namespace_to_use = namespace or (self.default_namespace if descriptor.namespaced else None)
        path = build_resource_path(
            group=group,
            version=version,
            resource=resource,
            namespaced=descriptor.namespaced,
            namespace=namespace_to_use,
        )
        payload = self.request_json(path, query={"limit": min(limit, 200), "continue": continue_token})
        metadata = payload.get("metadata") or {}
        return {
            "resource": {
                "group": group or "core",
                "version": version,
                "name": resource,
                "kind": descriptor.kind,
                "namespaced": descriptor.namespaced,
                "namespace": namespace_to_use if descriptor.namespaced else None,
                "verbs": descriptor.verbs,
            },
            "items": payload.get("items", []),
            "metadata": {
                "count": len(payload.get("items", [])),
                "continue": metadata.get("continue", ""),
                "resource_version": metadata.get("resourceVersion", ""),
            },
        }

    def get_resource(
        self,
        *,
        group: str,
        version: str,
        resource: str,
        name: str,
        namespace: str | None = None,
    ) -> dict[str, Any]:
        descriptor = self.get_resource_descriptor(group, version, resource)
        namespace_to_use = namespace or (self.default_namespace if descriptor.namespaced else None)
        path = build_resource_path(
            group=group,
            version=version,
            resource=resource,
            namespaced=descriptor.namespaced,
            namespace=namespace_to_use,
            name=name,
        )
        payload = self.request_json(path)
        return self._serialize_resource_detail(
            descriptor=descriptor,
            group=group,
            version=version,
            resource=resource,
            payload=payload,
            namespace=namespace_to_use,
        )

    def apply_resource(
        self,
        *,
        group: str,
        version: str,
        resource: str,
        name: str,
        namespace: str | None,
        manifest_text: str,
        dry_run: bool = False,
        force: bool = False,
        field_manager: str = "kuboard",
    ) -> dict[str, Any]:
        descriptor = self.get_resource_descriptor(group, version, resource)
        manifest, namespace_to_use = self._load_manifest_object(
            group=group,
            version=version,
            resource=resource,
            descriptor=descriptor,
            manifest_text=manifest_text,
            namespace=namespace,
            name=name,
        )

        path = build_resource_path(
            group=group,
            version=version,
            resource=resource,
            namespaced=descriptor.namespaced,
            namespace=namespace_to_use,
            name=name,
        )
        payload = self.request_json(
            path,
            method="PATCH",
            body=yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True).encode("utf-8"),
            content_type="application/apply-patch+yaml",
            query={
                "fieldManager": field_manager,
                "force": "true" if force else "false",
                "dryRun": "All" if dry_run else None,
            },
        )
        return self._serialize_resource_detail(
            descriptor=descriptor,
            group=group,
            version=version,
            resource=resource,
            payload=payload,
            namespace=namespace_to_use,
        )

    def create_resource(
        self,
        *,
        group: str,
        version: str,
        resource: str,
        namespace: str | None,
        manifest_text: str,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        descriptor = self.get_resource_descriptor(group, version, resource)
        manifest, namespace_to_use = self._load_manifest_object(
            group=group,
            version=version,
            resource=resource,
            descriptor=descriptor,
            manifest_text=manifest_text,
            namespace=namespace,
        )

        path = build_resource_path(
            group=group,
            version=version,
            resource=resource,
            namespaced=descriptor.namespaced,
            namespace=namespace_to_use,
        )
        payload = self.request_json(
            path,
            method="POST",
            body=json.dumps(manifest).encode("utf-8"),
            content_type="application/json",
            query={"dryRun": "All" if dry_run else None},
        )
        return self._serialize_resource_detail(
            descriptor=descriptor,
            group=group,
            version=version,
            resource=resource,
            payload=payload,
            namespace=(payload.get("metadata") or {}).get("namespace") or namespace_to_use,
        )

    def delete_resource(
        self,
        *,
        group: str,
        version: str,
        resource: str,
        name: str,
        namespace: str | None,
    ) -> dict[str, Any]:
        descriptor = self.get_resource_descriptor(group, version, resource)
        namespace_to_use = namespace or (self.default_namespace if descriptor.namespaced else None)
        path = build_resource_path(
            group=group,
            version=version,
            resource=resource,
            namespaced=descriptor.namespaced,
            namespace=namespace_to_use,
            name=name,
        )
        payload = self.request_json(path, method="DELETE")
        return {
            "resource": {
                "group": group or "core",
                "version": version,
                "name": resource,
                "kind": descriptor.kind,
                "namespaced": descriptor.namespaced,
                "namespace": namespace_to_use if descriptor.namespaced else None,
            },
            "result": payload,
        }

    def get_pod_logs(
        self,
        *,
        name: str,
        namespace: str | None = None,
        container: str | None = None,
        tail_lines: int = 200,
        previous: bool = False,
        timestamps: bool = True,
        since_time: str | None = None,
    ) -> dict[str, Any]:
        descriptor = self.get_resource_descriptor("", "v1", "pods")
        namespace_to_use = namespace or self.default_namespace
        path = (
            build_resource_path(
                group="",
                version="v1",
                resource="pods",
                namespaced=descriptor.namespaced,
                namespace=namespace_to_use,
                name=name,
            )
            + "/log"
        )
        payload = self.request_text(
            path,
            query={
                "container": container,
                "tailLines": max(10, min(tail_lines, 2000)),
                "previous": "true" if previous else None,
                "timestamps": "true" if timestamps else None,
                "sinceTime": since_time,
            },
        )
        lines = [line for line in payload.splitlines() if line.strip()]
        latest_timestamp = since_time or ""
        if timestamps:
            for line in lines:
                match = self.LOG_TIMESTAMP_RE.match(line)
                if match:
                    latest_timestamp = match.group("timestamp")
        return {
            "pod": name,
            "namespace": namespace_to_use,
            "container": container or "",
            "tail_lines": max(10, min(tail_lines, 2000)),
            "previous": previous,
            "timestamps": timestamps,
            "text": payload,
            "cursor": {
                "since_time": latest_timestamp or None,
                "line_count": len(lines),
            },
        }

    def exec_pod_command(
        self,
        *,
        name: str,
        namespace: str | None = None,
        container: str | None = None,
        shell_command: str,
        timeout_seconds: int = 15,
    ) -> dict[str, Any]:
        namespace_to_use, kubectl_path = self._prepare_pod_exec(name=name, namespace=namespace)

        if not shell_command.strip():
            raise KubernetesAPIError("执行命令不能为空。", status_code=400)

        command = ["/bin/sh", "-lc", shell_command]
        bounded_timeout = max(3, min(timeout_seconds, 60))

        with ExitStack() as stack:
            kubeconfig_file = stack.enter_context(
                tempfile.NamedTemporaryFile(mode="w", delete=False, encoding="utf-8")
            )
            kubeconfig_file.write(self.credential.get_kubeconfig())
            kubeconfig_file.flush()
            stack.callback(self._safe_remove, kubeconfig_file.name)

            args = [
                kubectl_path,
                "--kubeconfig",
                kubeconfig_file.name,
                "--request-timeout",
                f"{bounded_timeout}s",
            ]

            if self.impersonation:
                args.extend(["--as", self.impersonation.username])
                for group in self.impersonation.groups:
                    args.extend(["--as-group", group])

            args.extend(["exec", name, "-n", namespace_to_use])
            if container:
                args.extend(["-c", container])
            args.append("--")
            args.extend(command)

            started_at = time.monotonic()
            try:
                completed = subprocess.run(
                    args,
                    capture_output=True,
                    text=True,
                    timeout=bounded_timeout + 2,
                    check=False,
                )
            except subprocess.TimeoutExpired as exc:
                raise KubernetesAPIError(
                    "Pod Exec 执行超时。",
                    status_code=504,
                    details={
                        "timeout_seconds": bounded_timeout,
                        "command": command,
                        "partial_output": (exc.stdout or "")[:4000],
                    },
                ) from exc
            except OSError as exc:
                raise KubernetesAPIError(
                    f"无法启动 kubectl: {exc}",
                    status_code=500,
                    details={"command": args},
                ) from exc

        duration_ms = int((time.monotonic() - started_at) * 1000)
        stdout = completed.stdout or ""
        stderr = completed.stderr or ""
        return {
            "pod": name,
            "namespace": namespace_to_use,
            "container": container or "",
            "command": command,
            "shell_command": shell_command,
            "exit_code": completed.returncode,
            "success": completed.returncode == 0,
            "stdout": stdout[:20000],
            "stderr": stderr[:20000],
            "duration_ms": duration_ms,
            "output_excerpt": f"{stdout}\n{stderr}".strip()[:4000],
        }

    def open_pod_terminal(
        self,
        *,
        session,
        name: str,
        namespace: str | None = None,
        container: str | None = None,
        shell: str = "/bin/sh",
        rows: int = 32,
        cols: int = 120,
    ) -> dict[str, Any]:
        from apps.streams.terminal import TerminalSessionError, terminal_hub

        namespace_to_use, kubectl_path = self._prepare_pod_exec(name=name, namespace=namespace)
        try:
            payload = terminal_hub.open_session(
                session=session,
                kubeconfig_text=self.credential.get_kubeconfig(),
                kubectl_path=kubectl_path,
                impersonation_username=self.impersonation.username if self.impersonation else None,
                impersonation_groups=list(self.impersonation.groups) if self.impersonation else [],
                pod_name=name,
                namespace=namespace_to_use,
                container=container,
                shell=shell,
                rows=rows,
                cols=cols,
            )
        except TerminalSessionError as exc:
            raise KubernetesAPIError(str(exc), status_code=exc.status_code) from exc

        return {
            "pod": name,
            "namespace": namespace_to_use,
            "container": container or "",
            "shell": payload["shell"],
            "terminal": {
                "rows": payload["rows"],
                "cols": payload["cols"],
            },
            "text": payload["text"],
            "cursor": payload["cursor"],
        }

    def watch_resources(
        self,
        *,
        group: str,
        version: str,
        resource: str,
        namespace: str | None = None,
        resource_version: str | None = None,
        timeout_seconds: int = 10,
    ) -> dict[str, Any]:
        descriptor = self.get_resource_descriptor(group, version, resource)
        namespace_to_use = namespace or (self.default_namespace if descriptor.namespaced else None)
        path = build_resource_path(
            group=group,
            version=version,
            resource=resource,
            namespaced=descriptor.namespaced,
            namespace=namespace_to_use,
        )
        bounded_timeout = max(3, min(timeout_seconds, 30))
        raw_events = self.request_json_lines(
            path,
            query={
                "watch": "true",
                "allowWatchBookmarks": "true" if self.capability.supports_watch_bookmarks else None,
                "resourceVersion": resource_version,
                "timeoutSeconds": bounded_timeout,
            },
            timeout=bounded_timeout + 5,
        )

        events = []
        next_resource_version = resource_version or ""

        for event in raw_events:
            payload = event.get("object") or {}
            metadata = payload.get("metadata") or {}
            current_resource_version = metadata.get("resourceVersion", "")
            if current_resource_version:
                next_resource_version = current_resource_version
            events.append(
                {
                    "type": event.get("type", "UNKNOWN"),
                    "object": payload,
                    "metadata": {
                        "kind": payload.get("kind", ""),
                        "name": metadata.get("name", ""),
                        "namespace": metadata.get("namespace", ""),
                        "resource_version": current_resource_version,
                    },
                }
            )

        return {
            "resource": {
                "group": group or "core",
                "version": version,
                "name": resource,
                "kind": descriptor.kind,
                "namespaced": descriptor.namespaced,
                "namespace": namespace_to_use if descriptor.namespaced else None,
                "verbs": descriptor.verbs,
            },
            "events": events,
            "metadata": {
                "count": len(events),
                "resource_version": resource_version or "",
                "next_resource_version": next_resource_version,
                "timeout_seconds": bounded_timeout,
            },
        }

    def _serialize_resource_detail(
        self,
        *,
        descriptor: ResourceDescriptor,
        group: str,
        version: str,
        resource: str,
        payload: dict[str, Any],
        namespace: str | None,
    ) -> dict[str, Any]:
        metadata = payload.get("metadata") or {}
        return {
            "resource": {
                "group": group or "core",
                "version": version,
                "name": resource,
                "kind": descriptor.kind,
                "namespaced": descriptor.namespaced,
                "namespace": namespace if descriptor.namespaced else None,
                "verbs": descriptor.verbs,
            },
            "object": payload,
            "yaml": yaml.safe_dump(payload, sort_keys=False, allow_unicode=True),
            "metadata": {
                "name": metadata.get("name", ""),
                "namespace": metadata.get("namespace", ""),
                "uid": metadata.get("uid", ""),
                "resource_version": metadata.get("resourceVersion", ""),
                "generation": metadata.get("generation"),
            },
        }

    def _prepare_pod_exec(self, *, name: str, namespace: str | None) -> tuple[str, str]:
        if not self.capability.supports_exec:
            raise KubernetesAPIError("当前集群不支持 pods/exec。", status_code=501)

        kubectl_path = shutil.which("kubectl")
        if not kubectl_path:
            raise KubernetesAPIError("系统中未找到 kubectl，暂时无法执行 Pod Exec。", status_code=500)

        namespace_to_use = namespace or self.default_namespace
        permission_matrix = self.check_resource_permissions(
            group="",
            version="v1",
            resource="pods",
            namespace=namespace_to_use,
            name=name,
        )
        exec_permission = (permission_matrix.get("subresources") or {}).get("exec")
        if exec_permission and not exec_permission.get("allowed"):
            raise KubernetesAPIError(
                "当前账号没有 pods/exec 权限。",
                status_code=403,
                details=exec_permission,
            )
        return namespace_to_use, kubectl_path

    def _expected_api_version(self, group: str, version: str) -> str:
        return version if not group else f"{group}/{version}"

    def _load_manifest_object(
        self,
        *,
        group: str,
        version: str,
        resource: str,
        descriptor: ResourceDescriptor,
        manifest_text: str,
        namespace: str | None,
        name: str | None = None,
    ) -> tuple[dict[str, Any], str | None]:
        try:
            manifest = yaml.safe_load(manifest_text)
        except yaml.YAMLError as exc:
            raise KubernetesAPIError(f"YAML 解析失败: {exc}", status_code=400) from exc

        if not isinstance(manifest, dict):
            raise KubernetesAPIError("提交内容必须是一个 Kubernetes 对象。", status_code=400)

        expected_api_version = self._expected_api_version(group, version)
        manifest_api_version = manifest.get("apiVersion")
        if manifest_api_version and manifest_api_version != expected_api_version:
            raise KubernetesAPIError(
                f"manifest.apiVersion 应为 {expected_api_version}，当前为 {manifest_api_version}。",
                status_code=400,
            )
        manifest["apiVersion"] = expected_api_version

        manifest_kind = manifest.get("kind")
        if manifest_kind and descriptor.kind and manifest_kind != descriptor.kind:
            raise KubernetesAPIError(
                f"manifest.kind 应为 {descriptor.kind}，当前为 {manifest_kind}。",
                status_code=400,
            )
        if descriptor.kind:
            manifest["kind"] = descriptor.kind

        metadata = manifest.setdefault("metadata", {})
        if not isinstance(metadata, dict):
            raise KubernetesAPIError("metadata 字段必须是对象。", status_code=400)

        metadata_name = metadata.get("name")
        if name:
            if metadata_name and metadata_name != name:
                raise KubernetesAPIError("YAML 中的 metadata.name 与路径中的资源名称不一致。", status_code=400)
            metadata["name"] = name
        elif not metadata_name and not metadata.get("generateName"):
            raise KubernetesAPIError("新建资源时必须提供 metadata.name 或 metadata.generateName。", status_code=400)

        namespace_in_manifest = metadata.get("namespace")
        namespace_to_use = namespace or namespace_in_manifest or (self.default_namespace if descriptor.namespaced else None)
        if descriptor.namespaced:
            if namespace and namespace_in_manifest and namespace != namespace_in_manifest:
                raise KubernetesAPIError(
                    "manifest.metadata.namespace 与查询参数中的 namespace 不一致。",
                    status_code=400,
                )
            metadata["namespace"] = namespace_to_use
        else:
            metadata.pop("namespace", None)

        return manifest, namespace_to_use

    def sync_health(self) -> dict[str, Any]:
        try:
            probe = self.probe()
        except KubernetesAPIError as exc:
            self.cluster.status = ClusterStatus.ERROR
            self.cluster.health_state = ClusterHealthState.DEGRADED
            self.cluster.last_error = str(exc)
            self.cluster.save(update_fields=["status", "health_state", "last_error", "updated_at"])

            self.cluster.health.status = ClusterHealthState.DEGRADED
            self.cluster.health.message = str(exc)
            self.cluster.health.latency_ms = 0
            self.cluster.health.save(update_fields=["status", "message", "latency_ms", "last_checked_at"])
            raise

        version = probe["version"]
        self.cluster.status = ClusterStatus.READY
        self.cluster.health_state = ClusterHealthState.HEALTHY
        self.cluster.kube_version = version.get("gitVersion", "")
        self.cluster.last_error = ""
        self.cluster.last_seen_at = timezone.now()
        self.cluster.save(
            update_fields=["status", "health_state", "kube_version", "last_error", "last_seen_at", "updated_at"]
        )

        self.cluster.health.status = ClusterHealthState.HEALTHY
        self.cluster.health.message = f"连接成功，Kubernetes 版本 {version.get('gitVersion', 'unknown')}"
        self.cluster.health.latency_ms = probe["latency_ms"]
        self.cluster.health.save(update_fields=["status", "message", "latency_ms", "last_checked_at"])
        return probe

    def sync_capability_from_discovery(self, discovery: dict[str, Any]):
        groups = discovery["groups"]
        resource_index = discovery["resource_index"]
        supports_exec = bool(discovery.get("supports_exec"))

        self.capability.discovered_api_groups = [group["group"] for group in groups]
        self.capability.openapi_index = resource_index
        self.capability.supports_exec = supports_exec
        self.capability.last_synced_at = timezone.now()
        self.capability.save(
            update_fields=["discovered_api_groups", "openapi_index", "supports_exec", "last_synced_at"]
        )
