"""Which address the phone server may listen on (D-051): only the IPv4 address of a connected
network adapter whose network Windows treats as **Private**. Never on a Public network (cafés,
hotels, airports), and not on a work (domain) network either.

* Network List Manager (netlistmgr.h, COM): each connection's adapter ID, whether it is
  connected, and its network's category (NLM_NETWORK_CATEGORY_PUBLIC 0, PRIVATE 1,
  DOMAIN_AUTHENTICATED 2) and name. Called through comtypes' wrapper of its type library
  (generated at build time, packaging/build.py).
* Windows.Networking.Connectivity.NetworkInformation.GetHostNames (WinRT): the computer's IP
  addresses, each with its network adapter's ID, so the two can be matched.
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass

PUBLIC, PRIVATE, DOMAIN = 0, 1, 2
NETWORK_LIST_LIBRARY = ("{DCB00D01-570F-4A9B-8D69-199FDBA5723B}", 1, 0)
NETWORK_LIST_MANAGER = "{DCB00C01-570F-4A9B-8D69-199FDBA5723B}"
HOW_TO_PRIVATE = ("Settings → Network & internet → Wi-Fi (or Ethernet) → your network's "
                  "properties → Network profile type → Private network")


class NotAllowed(Exception):
    """No network the phone server may use, with what to do about it."""


@dataclass(frozen=True)
class Connection:
    adapter_id: str  # upper case, no braces
    connected: bool
    category: int
    network: str


@dataclass(frozen=True)
class Host:
    adapter_id: str
    ip: str


@dataclass(frozen=True)
class LanAddress:
    ip: str
    network: str


def _normal(adapter_id) -> str:
    return str(adapter_id).strip("{}").upper()


def choose(connections: list[Connection], hosts: list[Host]) -> LanAddress:
    """The address to listen on, or NotAllowed explaining why there is none."""
    connected = [c for c in connections if c.connected]
    for connection in connected:
        if connection.category != PRIVATE:
            continue
        for host in hosts:
            if host.adapter_id != connection.adapter_id:
                continue
            address = ipaddress.ip_address(host.ip)
            if address.version == 4 and address.is_private and not address.is_loopback:
                return LanAddress(host.ip, connection.network)
    public = [c for c in connected if c.category == PUBLIC]
    if public:
        raise NotAllowed(f"“{public[0].network}” is set up as a Public network, so Wisp won't "
                         f"open anything on it. If it's your home network, make it Private: "
                         f"{HOW_TO_PRIVATE}.")
    if any(c.category == DOMAIN for c in connected):
        raise NotAllowed("You're on a work (domain) network. Phone transfer only runs on a "
                         "Private home network.")
    raise NotAllowed("This PC isn't connected to a home network. Connect the PC and your phone "
                     "to the same Wi-Fi.")


def system_connections() -> list[Connection]:
    import comtypes.client

    networklist = comtypes.client.GetModule(NETWORK_LIST_LIBRARY)
    manager = comtypes.client.CreateObject(NETWORK_LIST_MANAGER,
                                           interface=networklist.INetworkListManager)
    found = []
    for item in manager.GetNetworkConnections():
        connection = item.QueryInterface(networklist.INetworkConnection)
        network = connection.GetNetwork()
        found.append(Connection(_normal(connection.GetAdapterId()), bool(connection.IsConnected),
                                int(network.GetCategory()), str(network.GetName())))
    return found


def system_hosts() -> list[Host]:
    from winrt.windows.networking import HostNameType
    from winrt.windows.networking.connectivity import NetworkInformation

    hosts = []
    for host in NetworkInformation.get_host_names():
        info = host.ip_information
        if host.type != HostNameType.IPV4 or info is None or info.network_adapter is None:
            continue
        hosts.append(Host(_normal(info.network_adapter.network_adapter_id), host.canonical_name))
    return hosts


def lan_address() -> LanAddress:
    return choose(system_connections(), system_hosts())
