"""SDN Controller Adapter.

This module translates structured remediation commands into controller-facing
payloads. The current implementation is intentionally mock-backed: it validates
and records what would be sent to a controller without touching real devices.
"""

from __future__ import annotations

import logging
import shlex
from typing import Any

from app.schemas import ControlCommand, ControlExecutionResult, SDNCommandPayload

logger = logging.getLogger(__name__)


class SDNControllerAdapter:
    """Compile and execute control commands against an SDN controller boundary."""

    controller_name = "mock-sdn-controller"

    async def compile(self, command: ControlCommand) -> SDNCommandPayload:
        """Compile a high-level ControlCommand into a controller payload."""

        operation, protocol, payload, rollback = self._compile_command(command)
        compiled = SDNCommandPayload(
            command_id=command.command_id,
            command_type=command.command_type,
            target=command.target,
            controller=self.controller_name,
            protocol=protocol,
            operation=operation,
            dry_run=command.dry_run,
            payload=payload,
            rollback=rollback,
            metadata={
                "source_command": command.command,
                "risk_level": command.risk_level,
                "requires_approval": command.requires_approval,
                "rationale": command.rationale,
            },
        )
        logger.info(
            "SDN command compiled command_id=%s type=%s protocol=%s operation=%s",
            command.command_id,
            command.command_type,
            protocol,
            operation,
        )
        return compiled

    async def dry_run(self, command: ControlCommand) -> ControlExecutionResult:
        """Validate a compiled command without dispatching it."""

        compiled = await self.compile(command)
        return self._result(
            command=command,
            compiled=compiled,
            status="dry_run_validated",
            success=True,
            message="SDN Controller Adapter 已完成 mock dry-run 校验，未真实下发到控制器。",
        )

    async def dispatch(self, command: ControlCommand, approved: bool = False) -> ControlExecutionResult:
        """Dispatch a command through the controller boundary.

        The implementation remains mock-only for now. Approval state is recorded
        so the result can prove whether a high-risk command passed the gate.
        """

        compiled = await self.compile(command)
        status = "approved_mock_dispatched" if approved else "mock_dispatched"
        return self._result(
            command=command,
            compiled=compiled,
            status=status,
            success=True,
            message=(
                "命令已通过 SDN Controller Adapter 的 mock 下发流程。"
                "当前未连接真实仿真控制器，未改变网络状态。"
            ),
        )

    def _compile_command(
        self,
        command: ControlCommand,
    ) -> tuple[str, str, dict[str, Any], dict[str, Any]]:
        args = self._parse_command_args(command.command)
        command_type = command.command_type

        if command_type == "collect_runtime_snapshot":
            return (
                "collect_runtime_snapshot",
                "ops-api",
                {
                    "device": args.get("device", command.target),
                    "metrics": self._split_csv(args.get("metrics", "")),
                },
                {},
            )
        if command_type == "run_connectivity_probe":
            return (
                "run_connectivity_probe",
                "ops-api",
                {
                    "target": args.get("target", command.target),
                    "count": self._int_arg(args.get("count"), 20),
                    "timeout_ms": self._int_arg(args.get("timeout-ms"), 1000),
                },
                {},
            )
        if command_type == "ap_client_audit":
            return (
                "audit_ap_clients",
                "wlan-controller",
                {
                    "ap": args.get("ap", command.target),
                    "top_talkers": self._int_arg(args.get("top-talkers"), 10),
                    "include_rssi": "include-rssi" in args,
                },
                {},
            )
        if command_type == "ap_channel_rebalance":
            return (
                "suggest_ap_channel_rebalance",
                "wlan-controller",
                {
                    "ap": args.get("ap", command.target),
                    "mode": args.get("mode", "suggest-only"),
                },
                {
                    "operation": "restore_previous_channel_plan",
                    "ap": args.get("ap", command.target),
                },
            )
        if command_type == "ap_client_balance":
            return (
                "suggest_ap_client_balance",
                "wlan-controller",
                {
                    "ap": args.get("ap", command.target),
                    "mode": args.get("mode", "suggest-only"),
                },
                {
                    "operation": "disable_temporary_client_balance_policy",
                    "ap": args.get("ap", command.target),
                },
            )
        if command_type == "ap_reachability_check":
            return (
                "ap_reachability_check",
                "ops-api",
                {
                    "ap": args.get("ap", command.target),
                    "include_ping": "include-ping" in args,
                    "include_snmp": "include-snmp" in args,
                },
                {},
            )
        if command_type == "poe_power_cycle":
            return (
                "poe_power_cycle",
                "switch-management",
                {
                    "ap": args.get("ap", command.target),
                    "dry_run": command.dry_run or "dry-run" in args,
                    "power_off_seconds": 10,
                },
                {
                    "operation": "ensure_poe_enabled",
                    "ap": args.get("ap", command.target),
                },
            )
        if command_type == "interface_error_audit":
            return (
                "interface_error_audit",
                "ops-api",
                {
                    "device": args.get("device", command.target),
                    "window": args.get("window", "30m"),
                },
                {},
            )
        if command_type == "traffic_topn_audit":
            return (
                "traffic_topn_audit",
                "ops-api",
                {
                    "device": args.get("device", command.target),
                    "window": args.get("window", "15m"),
                    "top": self._int_arg(args.get("top"), 10),
                },
                {},
            )
        if command_type == "prepare_link_failover":
            device = args.get("device", command.target)
            return (
                "prepare_openflow_failover_group",
                "openflow-1.3",
                {
                    "switch": device,
                    "intent": "prepare_link_failover",
                    "flow_mods": [
                        {
                            "type": "group_mod",
                            "group_type": "ff",
                            "match": {"eth_type": 2048},
                            "actions": ["output:primary_or_backup_port"],
                            "priority": 100,
                        }
                    ],
                    "dry_run": command.dry_run or "dry-run" in args,
                },
                {
                    "operation": "delete_system_created_failover_group",
                    "switch": device,
                },
            )
        if command_type == "manual_review_ticket":
            return (
                "create_manual_review_ticket",
                "ticketing",
                {"target": command.target, "source_command": command.command},
                {},
            )

        return (
            "unsupported_command_type",
            "mock",
            {
                "target": command.target,
                "source_command": command.command,
                "reason": "No adapter mapping yet; keep as manual review payload.",
            },
            {},
        )

    def _result(
        self,
        command: ControlCommand,
        compiled: SDNCommandPayload,
        status: str,
        success: bool,
        message: str,
    ) -> ControlExecutionResult:
        return ControlExecutionResult(
            command_id=command.command_id,
            command_type=command.command_type,
            target=command.target,
            command=command.command,
            controller=compiled.controller,
            protocol=compiled.protocol,
            operation=compiled.operation,
            dry_run=compiled.dry_run,
            status=status,
            success=success,
            message=message,
            compiled_payload=compiled,
        )

    @staticmethod
    def _parse_command_args(command: str) -> dict[str, str | bool]:
        parts = shlex.split(command)
        parsed: dict[str, str | bool] = {}
        index = 0
        while index < len(parts):
            token = parts[index]
            if token.startswith("--"):
                key = token[2:]
                if index + 1 < len(parts) and not parts[index + 1].startswith("--"):
                    parsed[key] = parts[index + 1]
                    index += 2
                else:
                    parsed[key] = True
                    index += 1
            else:
                index += 1
        return parsed

    @staticmethod
    def _split_csv(value: str | bool) -> list[str]:
        if not isinstance(value, str) or not value:
            return []
        return [item.strip() for item in value.split(",") if item.strip()]

    @staticmethod
    def _int_arg(value: str | bool | None, default: int) -> int:
        if not isinstance(value, str):
            return default
        try:
            return int(value)
        except ValueError:
            return default
