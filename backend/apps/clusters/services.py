from __future__ import annotations

import hashlib
import ipaddress
import logging
from dataclasses import dataclass
from urllib.parse import urlparse, urlunparse

import yaml
from rest_framework import serializers

logger = logging.getLogger(__name__)


@dataclass
class KubeconfigInspection:
    normalized: str
    server: str
    current_context: str
    cluster_count: int
    user_count: int
    context_count: int
    fingerprint: str


def _is_ip_address(host: str) -> bool:
    """判断给定字符串是否为合法的 IPv4 或 IPv6 地址。"""
    try:
        ipaddress.ip_address(host.strip("[]"))
        return True
    except ValueError:
        return False


def _replace_server_host(server_url: str, new_ip: str) -> str:
    """将 server URL 中的主机名替换为指定的 IP 地址，保留端口和路径。"""
    if not server_url or not new_ip:
        return server_url

    parsed = urlparse(server_url)
    port = parsed.port

    if ":" in new_ip:
        # IPv6 地址需要用方括号包裹
        new_netloc = f"[{new_ip}]:{port}" if port else f"[{new_ip}]"
    else:
        new_netloc = f"{new_ip}:{port}" if port else new_ip

    return urlunparse((parsed.scheme, new_netloc, parsed.path, parsed.params, parsed.query, parsed.fragment))


def _ensure_mapping(value, *, label: str):
    if not isinstance(value, dict):
        raise serializers.ValidationError(f"{label} 必须是对象。")
    return value


def validate_kubeconfig(raw_kubeconfig: str, *, server_override: str | None = None) -> KubeconfigInspection:
    try:
        payload = yaml.safe_load(raw_kubeconfig)
    except yaml.YAMLError as exc:
        raise serializers.ValidationError(f"kubeconfig YAML 解析失败: {exc}") from exc

    payload = _ensure_mapping(payload, label="kubeconfig")

    clusters = payload.get("clusters") or []
    users = payload.get("users") or []
    contexts = payload.get("contexts") or []

    if not clusters:
        raise serializers.ValidationError("kubeconfig 至少需要包含一个 cluster。")
    if not users:
        raise serializers.ValidationError("kubeconfig 至少需要包含一个 user。")
    if not contexts:
        raise serializers.ValidationError("kubeconfig 至少需要包含一个 context。")

    for user in users:
        user_data = _ensure_mapping(user, label="user entry")
        auth_data = _ensure_mapping(user_data.get("user") or {}, label="user auth")
        if "exec" in auth_data:
            raise serializers.ValidationError("当前版本默认拒绝导入包含 exec 认证插件的 kubeconfig。")
        if "auth-provider" in auth_data:
            raise serializers.ValidationError("当前版本默认拒绝导入包含 auth-provider 的 kubeconfig。")
        if auth_data.get("client-certificate") or auth_data.get("client-key"):
            raise serializers.ValidationError("当前版本默认拒绝引用本地 client certificate / key 文件路径的 kubeconfig。")

    cluster_servers = {}
    for cluster in clusters:
        cluster_entry = _ensure_mapping(cluster, label="cluster entry")
        cluster_name = cluster_entry.get("name")
        cluster_data = _ensure_mapping(cluster_entry.get("cluster") or {}, label="cluster config")
        if cluster_data.get("insecure-skip-tls-verify"):
            raise serializers.ValidationError(
                "当前版本默认拒绝 insecure-skip-tls-verify=true 的 kubeconfig。"
            )
        if cluster_data.get("certificate-authority"):
            raise serializers.ValidationError("当前版本默认拒绝引用本地 certificate-authority 文件路径的 kubeconfig。")

        original_server = cluster_data.get("server", "")

        # 如果提供了 server_override（用户手动指定的 IP 地址），
        # 检测 server URL 中是否包含非 IP 的主机名，若是则替换
        if server_override:
            parsed = urlparse(original_server)
            hostname = parsed.hostname
            if hostname and not _is_ip_address(hostname):
                resolved_server = _replace_server_host(original_server, server_override)
                cluster_data["server"] = resolved_server
                logger.info(
                    "kubeconfig 集群 %s 的 server 地址已从 %s 替换为 %s",
                    cluster_name,
                    original_server,
                    resolved_server,
                )
                cluster_servers[cluster_name] = resolved_server
            else:
                cluster_servers[cluster_name] = original_server
        else:
            cluster_servers[cluster_name] = original_server

    current_context_name = payload.get("current-context") or contexts[0].get("name")
    current_context = next(
        (context for context in contexts if context.get("name") == current_context_name),
        None,
    )
    if current_context is None:
        raise serializers.ValidationError("current-context 未在 contexts 中找到。")

    context_data = _ensure_mapping(current_context.get("context") or {}, label="context")
    cluster_name = context_data.get("cluster")
    if cluster_name not in cluster_servers:
        raise serializers.ValidationError("当前 context 指向的 cluster 不存在。")

    normalized = yaml.safe_dump(payload, sort_keys=False, allow_unicode=True)
    return KubeconfigInspection(
        normalized=normalized,
        server=cluster_servers[cluster_name],
        current_context=current_context_name,
        cluster_count=len(clusters),
        user_count=len(users),
        context_count=len(contexts),
        fingerprint=hashlib.sha256(normalized.encode("utf-8")).hexdigest(),
    )
