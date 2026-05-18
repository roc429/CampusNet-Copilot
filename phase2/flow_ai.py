# -*- coding: utf-8 -*-
import csv
import json
import os
import time
from datetime import datetime

from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import (
    CONFIG_DISPATCHER,
    MAIN_DISPATCHER,
    DEAD_DISPATCHER,
    set_ev_cls,
)
from ryu.ofproto import ofproto_v1_3
from ryu.lib import hub
from ryu.lib.packet import packet, ethernet, ether_types

from ryu.app.wsgi import ControllerBase, WSGIApplication, Response, route


APP_NAME = "campus_flow_ai"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")

TELEMETRY_FILE = os.environ.get(
    "TELEMETRY_FILE",
    os.path.join(DATA_DIR, "telemetry.csv")
)

MONITOR_INTERVAL = float(os.environ.get("MONITOR_INTERVAL", "5"))


def json_response(data, status=200):
    body = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
    return Response(
        content_type="application/json",
        charset="utf-8",
        body=body,
        status=status
    )


def switch_role(dpid):
    if dpid == 1:
        return "core"
    if dpid in (2, 3, 4):
        return "aggregation"
    if 5 <= dpid <= 8:
        return "teaching_ap"
    if 9 <= dpid <= 12:
        return "dorm_ap"
    if 13 <= dpid <= 16:
        return "data_access"
    return "unknown"


def estimate_port_bw_mbps(dpid, port_no):
    """
    按你的第一阶段拓扑估算端口带宽。
    这个映射和 campus.py 里的 bw 参数保持一致。
    """

    # s1 核心交换机，连接 s2/s3/s4，都是 1000 Mbps
    if dpid == 1:
        return 1000

    # s2 教学汇聚，port1 到核心 1000 Mbps，其余到接入 100 Mbps
    if dpid == 2:
        return 1000 if port_no == 1 else 100

    # s3 宿舍汇聚，port1 到核心 1000 Mbps，其余到接入 100 Mbps
    if dpid == 3:
        return 1000 if port_no == 1 else 100

    # s4 数据中心汇聚，所有主要链路 1000 Mbps
    if dpid == 4:
        return 1000

    # s5-s8 教学区接入，port1 上联 100 Mbps，主机端口 10 Mbps
    if 5 <= dpid <= 8:
        return 100 if port_no == 1 else 10

    # s9-s12 宿舍区接入，port1 上联 100 Mbps，主机端口 10 Mbps
    if 9 <= dpid <= 12:
        return 100 if port_no == 1 else 10

    # s13-s16 数据中心接入
    if 13 <= dpid <= 16:
        if port_no == 1:
            return 1000
        if dpid in (13, 14):
            return 100
        if dpid == 15:
            return 1000
        return 1000

    return 100


class CampusFlowAI(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    _CONTEXTS = {
        "wsgi": WSGIApplication
    }

    def __init__(self, *args, **kwargs):
        super(CampusFlowAI, self).__init__(*args, **kwargs)

        self.mac_to_port = {}
        self.datapaths = {}
        self.last_stats = {}
        self.latest_metrics = {}
        self.applied_policies = []
        self.next_meter_id = 1

        os.makedirs(os.path.dirname(TELEMETRY_FILE), exist_ok=True)
        self._ensure_telemetry_header()

        wsgi = kwargs["wsgi"]
        wsgi.register(PolicyRestController, {APP_NAME: self})

        self.monitor_thread = hub.spawn(self._monitor)

        self.logger.info("CampusFlowAI started")
        self.logger.info("Telemetry file: %s", TELEMETRY_FILE)

    def _ensure_telemetry_header(self):
        if os.path.exists(TELEMETRY_FILE):
            return

        with open(TELEMETRY_FILE, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "timestamp",
                "timestamp_iso",
                "dpid",
                "port",
                "role",
                "rx_bytes",
                "tx_bytes",
                "rx_packets",
                "tx_packets",
                "rx_dropped",
                "tx_dropped",
                "byte_delta",
                "packet_delta",
                "drop_delta",
                "throughput_bps",
                "port_bw_mbps",
                "load",
                "loss"
            ])

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        dp = ev.msg.datapath
        ofp = dp.ofproto
        parser = dp.ofproto_parser

        match = parser.OFPMatch()
        actions = [
            parser.OFPActionOutput(
                ofp.OFPP_CONTROLLER,
                ofp.OFPCML_NO_BUFFER
            )
        ]

        self.add_flow(dp, priority=0, match=match, actions=actions)

        self.logger.info("switch connected: dpid=%s", dp.id)

    @set_ev_cls(ofp_event.EventOFPStateChange, [MAIN_DISPATCHER, DEAD_DISPATCHER])
    def state_change_handler(self, ev):
        dp = ev.datapath

        if ev.state == MAIN_DISPATCHER:
            self.datapaths[dp.id] = dp
            self.logger.info("datapath registered: dpid=%s", dp.id)

        elif ev.state == DEAD_DISPATCHER:
            if dp.id in self.datapaths:
                del self.datapaths[dp.id]
                self.logger.info("datapath unregistered: dpid=%s", dp.id)

    def add_flow(
        self,
        dp,
        priority,
        match,
        actions=None,
        idle_timeout=0,
        hard_timeout=0,
        buffer_id=None,
        instructions=None
    ):
        parser = dp.ofproto_parser
        ofp = dp.ofproto

        if instructions is None:
            if actions is None:
                actions = []
            instructions = [
                parser.OFPInstructionActions(
                    ofp.OFPIT_APPLY_ACTIONS,
                    actions
                )
            ]

        kwargs = {
            "datapath": dp,
            "priority": priority,
            "match": match,
            "instructions": instructions,
            "idle_timeout": idle_timeout,
            "hard_timeout": hard_timeout
        }

        if buffer_id is not None:
            kwargs["buffer_id"] = buffer_id

        mod = parser.OFPFlowMod(**kwargs)
        dp.send_msg(mod)

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, ev):
        msg = ev.msg
        dp = msg.datapath
        ofp = dp.ofproto
        parser = dp.ofproto_parser
        in_port = msg.match["in_port"]

        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocol(ethernet.ethernet)

        if eth is None:
            return

        if eth.ethertype == ether_types.ETH_TYPE_LLDP:
            return

        dst = eth.dst
        src = eth.src
        dpid = dp.id

        self.mac_to_port.setdefault(dpid, {})
        self.mac_to_port[dpid][src] = in_port

        if dst in self.mac_to_port[dpid]:
            out_port = self.mac_to_port[dpid][dst]
        else:
            out_port = ofp.OFPP_FLOOD

        actions = [parser.OFPActionOutput(out_port)]

        if out_port != ofp.OFPP_FLOOD:
            match = parser.OFPMatch(
                in_port=in_port,
                eth_src=src,
                eth_dst=dst
            )
            self.add_flow(
                dp,
                priority=1,
                match=match,
                actions=actions,
                idle_timeout=60
            )

        data = None
        if msg.buffer_id == ofp.OFP_NO_BUFFER:
            data = msg.data

        out = parser.OFPPacketOut(
            datapath=dp,
            buffer_id=msg.buffer_id,
            in_port=in_port,
            actions=actions,
            data=data
        )
        dp.send_msg(out)

    def _monitor(self):
        while True:
            for dp in list(self.datapaths.values()):
                self._request_port_stats(dp)

            hub.sleep(MONITOR_INTERVAL)

    def _request_port_stats(self, dp):
        parser = dp.ofproto_parser
        ofp = dp.ofproto
        req = parser.OFPPortStatsRequest(dp, 0, ofp.OFPP_ANY)
        dp.send_msg(req)

    @set_ev_cls(ofp_event.EventOFPPortStatsReply, MAIN_DISPATCHER)
    def port_stats_reply_handler(self, ev):
        now = time.time()
        now_iso = datetime.fromtimestamp(now).isoformat(timespec="seconds")
        dpid = ev.msg.datapath.id
        ofp = ev.msg.datapath.ofproto

        rows = []

        for stat in ev.msg.body:
            port_no = stat.port_no

            if port_no >= ofp.OFPP_MAX:
                continue

            key = (dpid, port_no)
            last = self.last_stats.get(key)

            rx_bytes = int(stat.rx_bytes)
            tx_bytes = int(stat.tx_bytes)
            rx_packets = int(stat.rx_packets)
            tx_packets = int(stat.tx_packets)
            rx_dropped = int(stat.rx_dropped)
            tx_dropped = int(stat.tx_dropped)

            byte_delta = 0
            packet_delta = 0
            drop_delta = 0
            throughput_bps = 0.0
            load = 0.0
            loss = 0.0

            if last:
                dt = max(now - last["timestamp"], 0.001)

                byte_delta = max(
                    0,
                    rx_bytes + tx_bytes - last["rx_bytes"] - last["tx_bytes"]
                )
                packet_delta = max(
                    0,
                    rx_packets + tx_packets - last["rx_packets"] - last["tx_packets"]
                )
                drop_delta = max(
                    0,
                    rx_dropped + tx_dropped - last["rx_dropped"] - last["tx_dropped"]
                )

                throughput_bps = byte_delta * 8.0 / dt
                port_bw_mbps = estimate_port_bw_mbps(dpid, port_no)
                port_bw_bps = port_bw_mbps * 1000 * 1000

                load = min(throughput_bps / port_bw_bps, 1.0)

                total = packet_delta + drop_delta
                if total > 0:
                    loss = drop_delta / float(total)

            port_bw_mbps = estimate_port_bw_mbps(dpid, port_no)

            self.last_stats[key] = {
                "timestamp": now,
                "rx_bytes": rx_bytes,
                "tx_bytes": tx_bytes,
                "rx_packets": rx_packets,
                "tx_packets": tx_packets,
                "rx_dropped": rx_dropped,
                "tx_dropped": tx_dropped
            }

            row = {
                "timestamp": now,
                "timestamp_iso": now_iso,
                "dpid": dpid,
                "port": port_no,
                "role": switch_role(dpid),
                "rx_bytes": rx_bytes,
                "tx_bytes": tx_bytes,
                "rx_packets": rx_packets,
                "tx_packets": tx_packets,
                "rx_dropped": rx_dropped,
                "tx_dropped": tx_dropped,
                "byte_delta": byte_delta,
                "packet_delta": packet_delta,
                "drop_delta": drop_delta,
                "throughput_bps": throughput_bps,
                "port_bw_mbps": port_bw_mbps,
                "load": load,
                "loss": loss
            }

            self.latest_metrics[key] = row
            rows.append(row)

        if rows:
            self._append_telemetry_rows(rows)

    def _append_telemetry_rows(self, rows):
        with open(TELEMETRY_FILE, "a", newline="") as f:
            writer = csv.writer(f)
            for row in rows:
                writer.writerow([
                    row["timestamp"],
                    row["timestamp_iso"],
                    row["dpid"],
                    row["port"],
                    row["role"],
                    row["rx_bytes"],
                    row["tx_bytes"],
                    row["rx_packets"],
                    row["tx_packets"],
                    row["rx_dropped"],
                    row["tx_dropped"],
                    row["byte_delta"],
                    row["packet_delta"],
                    row["drop_delta"],
                    row["throughput_bps"],
                    row["port_bw_mbps"],
                    row["load"],
                    row["loss"]
                ])

    def apply_policy(self, policy):
        action = policy.get("action")

        if action == "do_nothing":
            return {
                "ok": True,
                "message": "no action"
            }

        if action in ("drop_host", "protect_server"):
            result = self._install_drop_policy(policy)

        elif action == "rate_limit_host":
            result = self._install_meter_policy(policy)

        else:
            return {
                "ok": False,
                "error": "unsupported action: {}".format(action)
            }

        record = {
            "timestamp": time.time(),
            "timestamp_iso": datetime.now().isoformat(timespec="seconds"),
            "policy": policy,
            "result": result
        }
        self.applied_policies.append(record)

        return result

    def _get_dp(self, policy):
        dpid = int(policy.get("dpid"))
        dp = self.datapaths.get(dpid)

        if dp is None:
            raise RuntimeError("datapath not connected: dpid={}".format(dpid))

        return dp

    def _build_match(self, parser, match_cfg):
        fields = {}

        eth_type = match_cfg.get("eth_type")
        if eth_type is not None:
            fields["eth_type"] = int(eth_type)

        if match_cfg.get("ipv4_src") or match_cfg.get("ipv4_dst"):
            fields.setdefault("eth_type", ether_types.ETH_TYPE_IP)

        if match_cfg.get("ipv4_src"):
            fields["ipv4_src"] = str(match_cfg["ipv4_src"])

        if match_cfg.get("ipv4_dst"):
            fields["ipv4_dst"] = str(match_cfg["ipv4_dst"])

        if match_cfg.get("ip_proto") is not None:
            fields["ip_proto"] = int(match_cfg["ip_proto"])

        if match_cfg.get("tcp_dst") is not None:
            fields["ip_proto"] = 6
            fields["tcp_dst"] = int(match_cfg["tcp_dst"])

        if match_cfg.get("udp_dst") is not None:
            fields["ip_proto"] = 17
            fields["udp_dst"] = int(match_cfg["udp_dst"])

        return parser.OFPMatch(**fields)

    def _install_drop_policy(self, policy):
        dp = self._get_dp(policy)
        parser = dp.ofproto_parser

        match_cfg = policy.get("match", {})
        match = self._build_match(parser, match_cfg)

        priority = int(policy.get("priority", 100))
        duration = int(policy.get("duration", 60))

        # 空 instructions 表示丢弃匹配流量
        mod = parser.OFPFlowMod(
            datapath=dp,
            priority=priority,
            match=match,
            instructions=[],
            idle_timeout=duration,
            hard_timeout=duration
        )
        dp.send_msg(mod)

        self.logger.warning(
            "drop policy installed: dpid=%s match=%s duration=%s",
            dp.id,
            match_cfg,
            duration
        )

        return {
            "ok": True,
            "action": policy.get("action"),
            "dpid": dp.id,
            "match": match_cfg,
            "duration": duration
        }

    def _install_meter_policy(self, policy):
        """
        rate_limit_host 使用 OpenFlow meter。
        如果当前 OVS 不支持 meter，建议在策略层改用 drop_host。
        """

        dp = self._get_dp(policy)
        ofp = dp.ofproto
        parser = dp.ofproto_parser

        meter_id = int(policy.get("meter_id", self.next_meter_id))
        self.next_meter_id = max(self.next_meter_id + 1, meter_id + 1)

        rate_kbps = int(policy.get("rate_kbps", 1000))
        burst_size = max(1, int(rate_kbps * 0.1))

        band = parser.OFPMeterBandDrop(
            rate=rate_kbps,
            burst_size=burst_size
        )

        meter_mod = parser.OFPMeterMod(
            datapath=dp,
            command=ofp.OFPMC_ADD,
            flags=ofp.OFPMF_KBPS,
            meter_id=meter_id,
            bands=[band]
        )
        dp.send_msg(meter_mod)

        match_cfg = policy.get("match", {})
        match = self._build_match(parser, match_cfg)

        actions = [
            parser.OFPActionOutput(ofp.OFPP_NORMAL)
        ]

        instructions = [
            parser.OFPInstructionMeter(meter_id),
            parser.OFPInstructionActions(
                ofp.OFPIT_APPLY_ACTIONS,
                actions
            )
        ]

        priority = int(policy.get("priority", 100))
        duration = int(policy.get("duration", 60))

        flow_mod = parser.OFPFlowMod(
            datapath=dp,
            priority=priority,
            match=match,
            instructions=instructions,
            idle_timeout=duration,
            hard_timeout=duration
        )
        dp.send_msg(flow_mod)

        self.logger.warning(
            "meter policy installed: dpid=%s match=%s rate_kbps=%s duration=%s",
            dp.id,
            match_cfg,
            rate_kbps,
            duration
        )

        return {
            "ok": True,
            "action": "rate_limit_host",
            "dpid": dp.id,
            "match": match_cfg,
            "rate_kbps": rate_kbps,
            "duration": duration
        }


class PolicyRestController(ControllerBase):
    def __init__(self, req, link, data, **config):
        super(PolicyRestController, self).__init__(req, link, data, **config)
        self.app = data[APP_NAME]

    @route("campus_policy", "/health", methods=["GET"])
    def health(self, req, **kwargs):
        return json_response({
            "ok": True,
            "switches": sorted(list(self.app.datapaths.keys())),
            "telemetry_file": TELEMETRY_FILE
        })

    @route("campus_policy", "/telemetry/latest", methods=["GET"])
    def latest_telemetry(self, req, **kwargs):
        data = []
        for (_, _), row in sorted(self.app.latest_metrics.items()):
            data.append(row)

        return json_response({
            "ok": True,
            "count": len(data),
            "data": data
        })

    @route("campus_policy", "/policy/apply", methods=["POST"])
    def apply_policy(self, req, **kwargs):
        try:
            raw = req.body.decode("utf-8")
            policy = json.loads(raw)
            result = self.app.apply_policy(policy)
            status = 200 if result.get("ok") else 400
            return json_response(result, status=status)

        except Exception as e:
            return json_response({
                "ok": False,
                "error": str(e)
            }, status=500)

    @route("campus_policy", "/policy/history", methods=["GET"])
    def policy_history(self, req, **kwargs):
        return json_response({
            "ok": True,
            "data": self.app.applied_policies[-50:]
        })