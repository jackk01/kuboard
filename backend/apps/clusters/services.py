from __future__ import annotations

import hashlib
import ipaddress
from pathlib import Path
from dataclasses import dataclass

import yaml
from rest_framework import serializers


@dataclass
class KubeconfigInspection:
    normalized: str
    server: str
    current_context: str
    cluster_count: int
    user_count: int
    context_count: int
    fingerprint: str


@dataclass
class LocalKubeconfigResult:
    source_path: str
    kubeconfig: str
    inspection: KubeconfigInspection


def _is_ip_address(host: str) -> bool:
    """判断给定字符串是否为合法的 IPv4 或 IPv6 地址。"""
    try:
        ipaddress.ip_address(host.strip("[]"))
        return True
    except ValueError:
        return False


def _ensure_mapping(value, *, label: str):
    if not isinstance(value, dict):
        raise serializers.ValidationError(f"{label} 必须是对象。")
    return value


def validate_kubeconfig(raw_kubeconfig: str) -> KubeconfigInspection:
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


def load_local_kubeconfig() -> LocalKubeconfigResult:
    kubeconfig_path = Path.home() / ".kube" / "config"

    if not kubeconfig_path.exists():
        raise serializers.ValidationError(f"未找到本地 kubeconfig 文件：{kubeconfig_path}")
    if not kubeconfig_path.is_file():
        raise serializers.ValidationError(f"本地 kubeconfig 路径不是文件：{kubeconfig_path}")

    try:
        raw_kubeconfig = kubeconfig_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise serializers.ValidationError(f"读取本地 kubeconfig 失败：{exc}") from exc

    inspection = validate_kubeconfig(raw_kubeconfig)
    return LocalKubeconfigResult(
        source_path=str(kubeconfig_path),
        kubeconfig=raw_kubeconfig,
        inspection=inspection,
    )
