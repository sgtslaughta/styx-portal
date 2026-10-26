from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2] / "deploy" / "k8s"


def _docs():
    return list(yaml.safe_load_all((ROOT / "instances.yaml").read_text()))


def _kind(kind):
    return [d for d in _docs() if d["kind"] == kind]


def test_namespace_pod_security_labels():
    (ns,) = _kind("Namespace")
    assert ns["metadata"]["name"] == "styx-instances"
    labels = ns["metadata"]["labels"]
    assert labels["pod-security.kubernetes.io/enforce"] == "baseline"
    assert labels["pod-security.kubernetes.io/warn"] == "restricted"


def test_no_cluster_scoped_kinds_and_role_is_namespaced():
    kinds = {d["kind"] for d in _docs()}
    assert not kinds & {"ClusterRole", "ClusterRoleBinding"}
    (role,) = _kind("Role")
    assert role["metadata"]["namespace"] == "styx-instances"
    resources = {r for rule in role["rules"] for r in rule["resources"]}
    assert resources == {"deployments", "services", "persistentvolumeclaims",
                         "pods", "pods/log"}
    (rb,) = _kind("RoleBinding")
    assert rb["subjects"][0] == {"kind": "ServiceAccount", "name": "styx-backend",
                                 "namespace": "styx"}


def test_policy_ingress_only_from_traefik():
    (cnp,) = _kind("CiliumNetworkPolicy")
    assert cnp["spec"]["endpointSelector"] == {}
    (ing,) = cnp["spec"]["ingress"]
    assert ing["fromEndpoints"] == [
        {"matchLabels": {"k8s:io.kubernetes.pod.namespace": "traefik"}}]


def test_quota_and_limitrange_present():
    (q,) = _kind("ResourceQuota")
    assert q["spec"]["hard"]["requests.amd.com/gpu"] == "3"
    assert _kind("LimitRange")


def test_listed_in_kustomization():
    k = yaml.safe_load((ROOT / "kustomization.yaml").read_text())
    assert "instances.yaml" in k["resources"]


def test_egress_deny_nodes_and_api():
    (cnp,) = _kind("CiliumNetworkPolicy")
    assert cnp["spec"]["egressDeny"] == [
        {"toEntities": ["host", "remote-node", "kube-apiserver"]}]
