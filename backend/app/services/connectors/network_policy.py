import ipaddress
import re
import dns.exception
import dns.resolver

from app.core.config import get_settings

BLOCKED_IPS = {
    ipaddress.ip_address("169.254.169.254"),
    ipaddress.ip_address("100.100.100.200"),
}


class NetworkPolicyError(ValueError):
    pass


def validate_destination(host: str) -> list[str]:
    settings = get_settings()
    normalized = host.strip().rstrip(".").lower()
    try:
        ipaddress.ip_address(normalized)
        valid_host = True
    except ValueError:
        valid_host = bool(re.fullmatch(r"(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)(?:\.(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?))*", normalized))
    if not normalized or not valid_host:
        raise NetworkPolicyError("Host is not permitted by the database connection policy")
    allowed_hosts = {item.strip().lower().rstrip(".") for item in settings.data_source_allowed_hosts.split(",") if item.strip()}
    allowed_networks = [ipaddress.ip_network(item.strip(), strict=False) for item in settings.data_source_allowed_cidrs.split(",") if item.strip()]
    try:
        addresses = [str(ipaddress.ip_address(normalized))]
    except ValueError:
        try:
            resolver = dns.resolver.Resolver()
            timeout = get_settings().data_source_connect_timeout_seconds
            resolver.timeout = timeout
            resolver.lifetime = timeout
            addresses = set()
            for record_type in ("A", "AAAA"):
                try:
                    addresses.update(answer.address for answer in resolver.resolve(normalized, record_type, lifetime=timeout))
                except dns.resolver.NoAnswer:
                    continue
            addresses = sorted(addresses)
        except (OSError, dns.exception.DNSException):
            raise NetworkPolicyError("The database host could not be resolved") from None
    if not addresses:
        raise NetworkPolicyError("The database host could not be resolved")
    exact_host_allowed = normalized in allowed_hosts
    if settings.app_env == "production":
        try:
            ipaddress.ip_address(normalized)
        except ValueError:
            raise NetworkPolicyError("Hosted connections must use a literal IP address approved by deployment policy") from None
    for item in addresses:
        address = ipaddress.ip_address(item)
        if address in BLOCKED_IPS or address.is_loopback or address.is_link_local or address.is_multicast or address.is_unspecified or address.is_reserved:
            if not (settings.app_env != "production" and settings.data_source_allow_localhost and address.is_loopback):
                raise NetworkPolicyError("The database host is blocked by network policy")
        if address.is_private and not (exact_host_allowed or any(address in network for network in allowed_networks)):
            if not (settings.app_env != "production" and settings.data_source_allow_private_networks):
                raise NetworkPolicyError("The database host is blocked by network policy")
        if settings.app_env == "production" and not (exact_host_allowed or any(address in network for network in allowed_networks)):
            raise NetworkPolicyError("The database host is not in the configured allowlist")
    return addresses
