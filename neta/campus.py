# -*- coding: utf-8 -*-
from mininet.topo import Topo
from mininet.link import TCLink

class CampusTopo(Topo):
    def __init__(self):
        Topo.__init__(self)

        # ========== 1. 核心层 ==========
        core = self.addSwitch('s1')

        # ========== 2. 汇聚层 ==========
        agg_teaching = self.addSwitch('s2')   # 教学区汇聚
        agg_dorm = self.addSwitch('s3')       # 宿舍区汇聚
        agg_data = self.addSwitch('s4')       # 数据中心汇聚

        # 核心-汇聚链路（高带宽）
        self.addLink(core, agg_teaching, bw=1000, delay='5ms', loss=0)
        self.addLink(core, agg_dorm, bw=1000, delay='5ms', loss=0)
        self.addLink(core, agg_data, bw=1000, delay='5ms', loss=0)

        # ========== 3. 接入层 ==========
        # 教学区接入交换机（4台）
        acc_teaching = []
        for i in range(4):
            sw = self.addSwitch('s{}'.format(i + 5))
            acc_teaching.append(sw)
            # 汇聚-接入链路
            self.addLink(agg_teaching, sw, bw=100, delay='2ms', loss=1)

        # 宿舍区接入交换机（4台）
        acc_dorm = []
        for i in range(4):
            sw = self.addSwitch('s{}'.format(i + 9))
            acc_dorm.append(sw)
            # 汇聚-接入链路
            self.addLink(agg_dorm, sw, bw=100, delay='2ms', loss=1)

        # 数据中心接入交换机（4台）
        acc_data = []
        for i in range(4):
            sw = self.addSwitch('s{}'.format(i + 13))
            acc_data.append(sw)
            # 汇聚-接入链路
            self.addLink(agg_data, sw, bw=1000, delay='1ms', loss=0)

        # ========== 4. 终端与服务器 ==========
        
        # 教学区主机（10台，IP: 192.168.1.10-19，网关 192.168.1.1）
        for i in range(10):
            ip = '192.168.1.{}/24'.format(i + 10)
            gateway = '192.168.1.1'
            h = self.addHost('h{}'.format(i + 1), 
                           ip=ip, 
                           defaultRoute='via {}'.format(gateway))
            # 连接到接入交换机（负载均衡）
            sw_index = i % 4
            self.addLink(h, acc_teaching[sw_index], bw=10, delay='1ms', loss=0)

        # 宿舍区主机（10台，IP: 192.168.2.10-19，网关 192.168.2.1）
        for i in range(10):
            ip = '192.168.2.{}/24'.format(i + 10)
            gateway = '192.168.2.1'
            h = self.addHost('h{}'.format(i + 11), 
                           ip=ip, 
                           defaultRoute='via {}'.format(gateway))
            # 连接到接入交换机（负载均衡）
            sw_index = i % 4
            self.addLink(h, acc_dorm[sw_index], bw=10, delay='1ms', loss=0)

        # 数据中心服务器
        # Web 服务器
        web = self.addHost('web', 
                          ip='192.168.3.100/24', 
                          defaultRoute='via 192.168.3.1')
        self.addLink(web, acc_data[0], bw=100, delay='1ms', loss=0)

        # DNS 服务器
        dns = self.addHost('dns', 
                          ip='192.168.3.101/24', 
                          defaultRoute='via 192.168.3.1')
        self.addLink(dns, acc_data[1], bw=100, delay='1ms', loss=0)

        # 网关服务器（多网段）
        gw = self.addHost('gw', 
                         ip='192.168.3.1/24', 
                         defaultRoute='via 192.168.3.1')
        self.addLink(gw, acc_data[2], bw=1000, delay='1ms', loss=0)

topos = {'campus': (lambda: CampusTopo())}