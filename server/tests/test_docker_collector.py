"""Tests for the Docker workload-discovery pack (offline — no SSH, no Docker)."""

from __future__ import annotations

from typing import Any

import pytest

from argus.discovery.base import Collector, DiscoveryResult
from argus.discovery.collectors import COLLECTORS
from argus.discovery.vendors import BUILTIN_PACKS, VENDOR_PACKS, Transport
from argus.discovery.vendors.docker import DockerCollector
from argus.discovery.vendors.docker.collector import _SEP
from argus.discovery.vendors.docker.models import (
    DockerHost,
    cluster_name,
    parse_hosts,
    status_from_state,
)
from argus.discovery.vendors.pack import WORKLOADS, VendorPack


def _row(project: str, name: str, state: str, image: str = "img:1") -> str:
    return _SEP.join((project, name, state, image))


class FakeRun:
    """Stands in for DockerCollector._run, keyed by host name."""

    def __init__(self, results: dict[str, tuple[int, str, str]]) -> None:
        self.results = results
        self.calls: list[str] = []

    async def __call__(self, host: DockerHost) -> tuple[int, str, str]:
        self.calls.append(host.name)
        return self.results.get(host.name, (0, "", ""))


# --- host inventory parsing ------------------------------------------------


class TestParseHosts:
    def test_parses_name_target_pairs(self) -> None:
        hosts = parse_hosts("cerebrum=cerebrum,thor=thor,helios=root@10.0.0.9")
        assert [(h.name, h.target) for h in hosts] == [
            ("cerebrum", "cerebrum"),
            ("thor", "thor"),
            ("helios", "root@10.0.0.9"),
        ]

    def test_binary_override_applies_per_host(self) -> None:
        hosts = parse_hosts("thor=thor,amp=amp", "thor=/share/x/bin/docker")
        by_name = {h.name: h.binary for h in hosts}
        assert by_name["thor"] == "/share/x/bin/docker"
        assert by_name["amp"] == "docker"

    def test_local_target_skips_ssh(self) -> None:
        (host,) = parse_hosts("spark=local")
        assert host.is_local

    def test_malformed_entries_are_skipped_not_raised(self) -> None:
        """One typo in a fleet-wide list must not take discovery down for the rest."""
        hosts = parse_hosts("good=good,,garbage,=novalue,noequals")
        assert [h.name for h in hosts] == ["good"]

    def test_duplicate_host_names_keep_the_first(self) -> None:
        hosts = parse_hosts("a=one,a=two")
        assert [(h.name, h.target) for h in hosts] == [("a", "one")]


class TestValueMapping:
    @pytest.mark.parametrize(
        ("state", "expected"),
        [("running", "active"), ("restarting", "active"), ("exited", "offline"),
         ("paused", "offline"), ("dead", "offline"), ("created", "offline")],
    )
    def test_known_states_map(self, state: str, expected: str) -> None:
        assert status_from_state(state) == expected

    def test_unknown_state_is_offline_not_active(self) -> None:
        """A state Docker adds later must never be reported as healthy."""
        assert status_from_state("teleported") == "offline"
        assert status_from_state(None) == "offline"

    def test_cluster_name_is_qualified_by_host(self) -> None:
        """Compose project names are unique per host, not globally."""
        assert cluster_name("thor", "media") != cluster_name("cerebrum", "media")

    def test_container_with_no_compose_project_is_named_not_dropped(self) -> None:
        assert cluster_name("spark", None).endswith("/unstacked")


# --- collection ------------------------------------------------------------


class TestCollect:
    async def test_normalizes_stacks_and_containers(self, monkeypatch) -> None:
        collector = DockerCollector(hosts=[DockerHost("cerebrum", "cerebrum")])
        monkeypatch.setattr(
            collector,
            "_run",
            FakeRun({"cerebrum": (0, "\n".join([
                _row("infra", "aria-prometheus", "running"),
                _row("infra", "aria-grafana", "running"),
                _row("argus", "argus-netbox-1", "exited"),
            ]), "")}),
        )
        result = await collector.collect()

        assert [c.name for c in result.clusters] == ["cerebrum/argus", "cerebrum/infra"]
        assert all(c.host == "cerebrum" for c in result.clusters)
        by_name = {vm.name: vm for vm in result.virtual_machines}
        assert by_name["aria-prometheus"].cluster == "cerebrum/infra"
        assert by_name["aria-prometheus"].status == "active"
        assert by_name["argus-netbox-1"].status == "offline"
        assert result.devices == []  # workload plane only, by design

    async def test_a_host_with_no_docker_reconciles_to_zero(self, monkeypatch) -> None:
        collector = DockerCollector(hosts=[DockerHost("loki", "loki")])
        monkeypatch.setattr(
            collector, "_run",
            FakeRun({"loki": (127, "", "sh: docker: command not found")}),
        )
        result = await collector.collect()
        assert result.virtual_machines == []
        assert result.unreachable_hosts == []  # a real zero, not an unknown
        assert any("no docker runtime" in n for n in result.notes)

    async def test_an_unreachable_host_is_not_an_empty_host(self, monkeypatch) -> None:
        """The distinction that keeps an SSH blip from proposing to empty a stack."""
        collector = DockerCollector(hosts=[DockerHost("amp", "amp")])
        monkeypatch.setattr(
            collector, "_run",
            FakeRun({"amp": (255, "", "ssh: connect to host amp port 22: No route to host")}),
        )
        result = await collector.collect()
        assert result.unreachable_hosts == ["amp"]
        assert result.virtual_machines == []

    async def test_permission_denied_is_reported_verbatim(self, monkeypatch) -> None:
        """A root-owned socket looked exactly like a down host until the reason was kept."""
        collector = DockerCollector(hosts=[DockerHost("amp", "amp")])
        monkeypatch.setattr(
            collector, "_run",
            FakeRun({"amp": (1, "", "permission denied while trying to connect to the docker API")}),
        )
        result = await collector.collect()
        assert result.unreachable_hosts == ["amp"]
        assert any("permission denied" in n for n in result.notes)

    async def test_one_bad_host_does_not_lose_the_others(self, monkeypatch) -> None:
        collector = DockerCollector(
            hosts=[DockerHost("cerebrum", "cerebrum"), DockerHost("amp", "amp")]
        )
        monkeypatch.setattr(collector, "_run", FakeRun({
            "cerebrum": (0, _row("infra", "aria-redis", "running"), ""),
            "amp": (255, "", "ssh: no route to host"),
        }))
        result = await collector.collect()
        assert [vm.name for vm in result.virtual_machines] == ["aria-redis"]
        assert result.unreachable_hosts == ["amp"]

    async def test_output_is_ordered_regardless_of_which_host_answers_first(
        self, monkeypatch
    ) -> None:
        collector = DockerCollector(
            hosts=[DockerHost("thor", "thor"), DockerHost("cerebrum", "cerebrum")]
        )
        monkeypatch.setattr(collector, "_run", FakeRun({
            "thor": (0, _row("leeloo", "leeloo-gateway-1", "running"), ""),
            "cerebrum": (0, _row("infra", "aria-redis", "running"), ""),
        }))
        result = await collector.collect()
        assert [c.name for c in result.clusters] == ["cerebrum/infra", "thor/leeloo"]

    async def test_malformed_rows_are_skipped(self, monkeypatch) -> None:
        collector = DockerCollector(hosts=[DockerHost("h", "h")])
        monkeypatch.setattr(collector, "_run", FakeRun({
            "h": (0, "\n".join(["garbage", "", _SEP.join(("a", "", "running", "i")),
                                _row("ok", "good", "running")]), ""),
        }))
        result = await collector.collect()
        assert [vm.name for vm in result.virtual_machines] == ["good"]

    async def test_no_hosts_configured_is_a_note_not_a_crash(self) -> None:
        result = await DockerCollector(hosts=[]).collect()
        assert isinstance(result, DiscoveryResult)
        assert result.clusters == []
        assert any("DOCKER_HOSTS" in n for n in result.notes)

    def test_local_host_argv_has_no_ssh(self) -> None:
        argv = DockerCollector(hosts=[])._argv(DockerHost("spark", "local"))
        assert argv[0] == "sh"
        assert "ssh" not in argv

    def test_remote_host_argv_uses_batchmode(self) -> None:
        """BatchMode keeps a missing key from hanging discovery on a password prompt."""
        argv = DockerCollector(hosts=[])._argv(DockerHost("thor", "thor", "/x/docker"))
        assert argv[0] == "ssh"
        assert "BatchMode=yes" in argv
        assert "/x/docker ps -a" in argv[-1]


# --- pack registration -----------------------------------------------------


class TestPackRegistration:
    def test_docker_is_a_builtin_pack(self) -> None:
        pack = VENDOR_PACKS["docker"]
        assert isinstance(pack, VendorPack)
        assert pack.transport is Transport.HOST_SSH
        assert WORKLOADS in pack.capabilities
        assert pack.collector is DockerCollector
        assert pack in BUILTIN_PACKS

    def test_collector_is_resolvable_by_name(self) -> None:
        assert COLLECTORS["docker"] is DockerCollector
        assert issubclass(DockerCollector, Collector)

    def test_pack_declares_the_config_it_consumes(self) -> None:
        assert set(VENDOR_PACKS["docker"].config_vars) == {
            "DOCKER_HOSTS", "DOCKER_BINARIES", "DOCKER_SSH_TIMEOUT",
        }

    def test_metadata_reports_configured_hosts(self) -> None:
        meta: dict[str, Any] = DockerCollector(hosts=[DockerHost("a", "a")]).metadata()
        assert meta["hosts"] == ["a"]
