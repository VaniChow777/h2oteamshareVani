#!/usr/bin/env python3
"""Passive domain and customer-service email health audit.

This script intentionally avoids paid APIs. It uses `dig` when available and
Python stdlib fallbacks for HTTP/TLS checks. Active inbox/spam placement must be
measured separately with authorized seed inboxes.
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import socket
import ssl
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen


COMMON_DKIM_SELECTORS = [
    "default",
    "selector1",
    "selector2",
    "google",
    "k1",
    "s1",
    "s2",
    "mail",
    "smtp",
    "zendesk1",
    "zendesk2",
]

DNSBL_ZONES = [
    "zen.spamhaus.org",
    "b.barracudacentral.org",
    "bl.spamcop.net",
]


@dataclass
class Finding:
    severity: str
    category: str
    message: str
    evidence: str = ""
    fix: str = ""


@dataclass
class DomainInput:
    domain: str
    mailboxes: list[str] = field(default_factory=list)
    dkim_selectors: list[str] = field(default_factory=list)
    expected_mx: str = ""
    priority: str = ""
    notes: str = ""


def split_list(value: str) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.replace(";", ",").split(",") if item.strip()]


def load_domains(path: Path) -> list[DomainInput]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        domains = []
        for row in reader:
            domain = (row.get("domain") or "").strip().lower().rstrip(".")
            if not domain:
                continue
            domains.append(
                DomainInput(
                    domain=domain,
                    mailboxes=split_list(row.get("mailboxes", "")),
                    dkim_selectors=split_list(row.get("dkim_selectors", "")),
                    expected_mx=(row.get("expected_mx") or "").strip(),
                    priority=(row.get("priority") or "").strip(),
                    notes=(row.get("notes") or "").strip(),
                )
            )
    return domains


def run_dig(name: str, record_type: str) -> list[str]:
    if not shutil.which("dig"):
        return []
    try:
        result = subprocess.run(
            ["dig", "+short", record_type, name],
            check=False,
            capture_output=True,
            text=True,
            timeout=12,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if result.returncode != 0:
        return []
    return [line.strip().strip('"') for line in result.stdout.splitlines() if line.strip()]


def dns_lookup(name: str, record_type: str) -> list[str]:
    values = run_dig(name, record_type)
    if values or record_type not in {"A", "AAAA"}:
        return values
    family = socket.AF_INET if record_type == "A" else socket.AF_INET6
    try:
        records = socket.getaddrinfo(name, None, family, socket.SOCK_STREAM)
    except socket.gaierror:
        return []
    return sorted({record[4][0] for record in records})


def txt_lookup(name: str) -> list[str]:
    return dns_lookup(name, "TXT")


def https_check(domain: str) -> dict[str, Any]:
    result: dict[str, Any] = {"reachable": False}
    url = f"https://{domain}/"
    try:
        request = Request(url, headers={"User-Agent": "domain-email-health-auditor/1.0"})
        with urlopen(request, timeout=12) as response:
            result.update(
                {
                    "reachable": True,
                    "status": getattr(response, "status", None),
                    "final_url": response.geturl(),
                }
            )
    except Exception as exc:  # noqa: BLE001 - diagnostic tool should capture failures.
        result["error"] = str(exc)

    try:
        context = ssl.create_default_context()
        with socket.create_connection((domain, 443), timeout=8) as sock:
            with context.wrap_socket(sock, server_hostname=domain) as tls:
                cert = tls.getpeercert()
                result["tls_subject"] = cert.get("subject")
                result["tls_issuer"] = cert.get("issuer")
                result["tls_not_after"] = cert.get("notAfter")
    except Exception as exc:  # noqa: BLE001
        result["tls_error"] = str(exc)
    return result


def fetch_url(url: str, timeout: int = 12) -> dict[str, Any]:
    started = time.monotonic()
    result: dict[str, Any] = {"url": url, "reachable": False}
    try:
        request = Request(url, headers={"User-Agent": "domain-email-health-auditor/1.0"})
        with urlopen(request, timeout=timeout) as response:
            body_sample = response.read(2048)
            result.update(
                {
                    "reachable": True,
                    "status": getattr(response, "status", None),
                    "final_url": response.geturl(),
                    "elapsed_ms": round((time.monotonic() - started) * 1000),
                    "content_type": response.headers.get("content-type", ""),
                    "sample_bytes": len(body_sample),
                }
            )
    except Exception as exc:  # noqa: BLE001
        result.update(
            {
                "error": str(exc),
                "elapsed_ms": round((time.monotonic() - started) * 1000),
            }
        )
    return result


def web_entrypoint_checks(domain: str) -> list[dict[str, Any]]:
    return [
        fetch_url(f"https://{domain}/"),
        fetch_url(f"http://{domain}/"),
        fetch_url(f"https://www.{domain}/"),
        fetch_url(f"http://www.{domain}/"),
    ]


def smtp_starttls_check(host: str) -> dict[str, Any]:
    result: dict[str, Any] = {"host": host, "reachable": False}
    try:
        with socket.create_connection((host, 25), timeout=8) as sock:
            sock.settimeout(8)
            banner = sock.recv(512).decode("utf-8", errors="replace").strip()
            sock.sendall(b"EHLO domain-email-health-auditor.local\r\n")
            ehlo = sock.recv(2048).decode("utf-8", errors="replace")
            result.update(
                {
                    "reachable": True,
                    "banner": banner,
                    "starttls": "STARTTLS" in ehlo.upper(),
                }
            )
            sock.sendall(b"QUIT\r\n")
    except Exception as exc:  # noqa: BLE001
        result["error"] = str(exc)
    return result


def mx_hosts(mx_records: list[str]) -> list[str]:
    hosts = []
    for record in mx_records:
        parts = record.split()
        if not parts:
            continue
        host = parts[-1].rstrip(".")
        if host == "":
            continue
        hosts.append(host)
    return hosts


def has_null_mx(mx_records: list[str]) -> bool:
    return any(record.split() and record.split()[-1].strip() == "." for record in mx_records)


def check_dnsbl(ip: str) -> list[str]:
    if ":" in ip:
        return []
    reversed_ip = ".".join(reversed(ip.split(".")))
    listed = []
    for zone in DNSBL_ZONES:
        query = f"{reversed_ip}.{zone}"
        if dns_lookup(query, "A"):
            listed.append(zone)
    return listed


def analyze_domain(item: DomainInput, check_smtp: bool) -> dict[str, Any]:
    domain = item.domain
    findings: list[Finding] = []
    records = {
        "a": dns_lookup(domain, "A"),
        "aaaa": dns_lookup(domain, "AAAA"),
        "ns": dns_lookup(domain, "NS"),
        "soa": dns_lookup(domain, "SOA"),
        "mx": dns_lookup(domain, "MX"),
        "txt": txt_lookup(domain),
        "caa": dns_lookup(domain, "CAA"),
        "dmarc": txt_lookup(f"_dmarc.{domain}"),
        "mta_sts": txt_lookup(f"_mta-sts.{domain}"),
        "tls_rpt": txt_lookup(f"_smtp._tls.{domain}"),
        "bimi": txt_lookup(f"default._bimi.{domain}"),
    }

    if not records["a"] and not records["aaaa"]:
        findings.append(Finding("high", "dns", "Domain has no A/AAAA record", fix="Confirm the domain should host a site; publish A/AAAA or document why it is mail-only."))
    if not records["ns"]:
        findings.append(Finding("critical", "dns", "Domain has no NS records", fix="Fix nameserver delegation at the registrar/DNS provider."))
    null_mx = has_null_mx(records["mx"])
    if null_mx:
        severity = "critical" if item.mailboxes else "medium"
        findings.append(Finding(severity, "mail-routing", "Domain publishes Null MX and declares it does not accept mail", evidence=" | ".join(records["mx"]), fix="Remove Null MX and publish provider MX records if customer-service mailboxes use this domain."))
    elif not records["mx"]:
        findings.append(Finding("critical", "mail-routing", "Domain has no MX records", fix="Publish MX records for the mailbox provider."))

    spf_records = [txt for txt in records["txt"] if txt.lower().startswith("v=spf1")]
    if not spf_records:
        findings.append(Finding("high", "spf", "Missing SPF record", fix="Publish a single SPF record that covers all legitimate senders."))
    elif len(spf_records) > 1:
        findings.append(Finding("critical", "spf", "Multiple SPF records found", evidence=" | ".join(spf_records), fix="Merge all sender mechanisms into one SPF record."))
    else:
        spf = spf_records[0]
        if "+all" in spf.lower():
            findings.append(Finding("critical", "spf", "SPF uses +all", evidence=spf, fix="Replace +all with ~all or -all after validating senders."))
        elif not any(token in spf.lower() for token in ["-all", "~all"]):
            findings.append(Finding("medium", "spf", "SPF does not end with a clear all mechanism", evidence=spf, fix="Add ~all during migration or -all after validation."))

    dmarc_records = [txt for txt in records["dmarc"] if txt.lower().startswith("v=dmarc1")]
    if not dmarc_records:
        findings.append(Finding("high", "dmarc", "Missing DMARC record", fix="Publish _dmarc TXT with p=none and rua, then tighten after alignment is verified."))
    else:
        dmarc = dmarc_records[0]
        lower = dmarc.lower()
        if "p=none" in lower:
            findings.append(Finding("low", "dmarc", "DMARC is monitoring only", evidence=dmarc, fix="Move toward quarantine/reject after active alignment passes."))
        if "rua=" not in lower:
            findings.append(Finding("medium", "dmarc", "DMARC has no aggregate report address", evidence=dmarc, fix="Add rua=mailto: address monitored by the owner or a DMARC platform."))

    selectors = item.dkim_selectors or COMMON_DKIM_SELECTORS
    dkim_found = {}
    for selector in selectors:
        value = txt_lookup(f"{selector}._domainkey.{domain}")
        if value:
            dkim_found[selector] = value
    if item.dkim_selectors and not dkim_found:
        findings.append(Finding("high", "dkim", "None of the expected DKIM selectors were found", evidence=", ".join(item.dkim_selectors), fix="Enable DKIM in the sender provider and publish selector TXT/CNAME records."))
    elif not dkim_found:
        findings.append(Finding("medium", "dkim", "No common DKIM selectors found", evidence=", ".join(COMMON_DKIM_SELECTORS), fix="Supply provider selectors or verify DKIM through active message headers."))

    if not records["mta_sts"]:
        findings.append(Finding("low", "mta-sts", "Missing MTA-STS TXT record", fix="Publish MTA-STS and hosted policy if inbound TLS policy matters."))
    if not records["tls_rpt"]:
        findings.append(Finding("low", "tls-rpt", "Missing SMTP TLS reporting record", fix="Publish _smtp._tls TXT with a monitored rua address."))

    https = https_check(domain)
    if not https.get("reachable"):
        findings.append(Finding("medium", "https", "HTTPS check failed", evidence=https.get("error", ""), fix="Fix website TLS/hosting if customers use this domain in support flows."))
    if https.get("tls_error"):
        findings.append(Finding("medium", "tls", "TLS certificate check failed", evidence=https["tls_error"], fix="Renew or correct the certificate chain."))

    web_entrypoints = web_entrypoint_checks(domain)
    reachable_entrypoints = [entry for entry in web_entrypoints if entry.get("reachable")]
    if not reachable_entrypoints:
        findings.append(Finding("high", "web-experience", "No common web entrypoints are reachable", evidence="; ".join(f"{entry['url']}: {entry.get('error', '')}" for entry in web_entrypoints), fix="Make at least the canonical HTTPS entrypoint reachable and redirect non-canonical variants to it."))
    else:
        slow_entrypoints = [entry for entry in reachable_entrypoints if entry.get("elapsed_ms", 0) > 5000]
        if slow_entrypoints:
            evidence = "; ".join(f"{entry['url']} {entry['elapsed_ms']}ms" for entry in slow_entrypoints)
            findings.append(Finding("medium", "web-performance", "One or more web entrypoints are slow", evidence=evidence, fix="Check CDN, origin latency, TLS handshake, redirects, and blocking resources."))
        insecure_final = [
            entry for entry in reachable_entrypoints
            if entry["url"].startswith("http://") and str(entry.get("final_url", "")).startswith("http://")
        ]
        if insecure_final:
            evidence = "; ".join(f"{entry['url']} -> {entry.get('final_url')}" for entry in insecure_final)
            findings.append(Finding("medium", "web-security", "HTTP entrypoint does not upgrade to HTTPS", evidence=evidence, fix="Redirect all HTTP traffic to canonical HTTPS while preserving path and query parameters."))

    mx = mx_hosts(records["mx"])
    mx_resolution = {host: {"a": dns_lookup(host, "A"), "aaaa": dns_lookup(host, "AAAA")} for host in mx}
    for host, resolved in mx_resolution.items():
        if not resolved["a"] and not resolved["aaaa"]:
            findings.append(Finding("critical", "mail-routing", "MX host does not resolve", evidence=host, fix="Correct or remove the broken MX host."))

    smtp = []
    if check_smtp:
        smtp = [smtp_starttls_check(host) for host in mx[:3]]
        for smtp_result in smtp:
            if smtp_result.get("reachable") and not smtp_result.get("starttls"):
                findings.append(Finding("medium", "smtp", "MX does not advertise STARTTLS", evidence=smtp_result["host"], fix="Enable STARTTLS on inbound MX or confirm provider policy."))

    listed = {}
    for ip in records["a"]:
        zones = check_dnsbl(ip)
        if zones:
            listed[ip] = zones
            findings.append(Finding("high", "reputation", "Domain A record IP appears on DNSBL", evidence=f"{ip}: {', '.join(zones)}", fix="Investigate hosting reputation; request delisting or move clean hosting if needed."))

    score = score_findings(findings)
    return {
        "domain": domain,
        "mailboxes": item.mailboxes,
        "priority": item.priority,
        "expected_mx": item.expected_mx,
        "notes": item.notes,
        "score": score,
        "status": classify(score, findings),
        "records": records,
        "dkim_found": dkim_found,
        "https": https,
        "web_entrypoints": web_entrypoints,
        "mx_hosts": mx,
        "mx_resolution": mx_resolution,
        "smtp": smtp,
        "dnsbl": listed,
        "findings": [finding.__dict__ for finding in findings],
    }


def score_findings(findings: list[Finding]) -> int:
    penalty = 0
    weights = {"critical": 30, "high": 20, "medium": 10, "low": 4}
    for finding in findings:
        penalty += weights.get(finding.severity, 5)
    return max(0, 100 - penalty)


def classify(score: int, findings: list[Finding]) -> str:
    if any(f.severity == "critical" for f in findings) or score < 50:
        return "Critical"
    if score < 70:
        return "At Risk"
    if score < 85:
        return "Watch"
    return "Healthy"


def markdown_report(results: list[dict[str, Any]]) -> str:
    lines = [
        "# Domain Email Health Audit",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        "",
        "## Scorecard",
        "",
        "| Domain | Score | Status | Findings |",
        "|---|---:|---|---:|",
    ]
    for item in results:
        lines.append(f"| {item['domain']} | {item['score']} | {item['status']} | {len(item['findings'])} |")
    lines.extend(["", "## Priority Findings", ""])
    for item in results:
        if not item["findings"]:
            continue
        lines.append(f"### {item['domain']} ({item['status']}, {item['score']})")
        lines.append("")
        for finding in item["findings"]:
            evidence = f" Evidence: {finding['evidence']}" if finding.get("evidence") else ""
            fix = f" Fix: {finding['fix']}" if finding.get("fix") else ""
            lines.append(f"- **{finding['severity'].upper()} / {finding['category']}**: {finding['message']}.{evidence}{fix}")
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Passive domain and customer-service email health audit")
    parser.add_argument("--input", required=True, type=Path, help="CSV with domain,mailboxes,dkim_selectors,expected_mx,priority,notes")
    parser.add_argument("--output", type=Path, help="Output report path. Defaults to stdout.")
    parser.add_argument("--format", choices=["json", "md"], default="json")
    parser.add_argument("--check-smtp", action="store_true", help="Try SMTP port 25 and STARTTLS checks for MX hosts.")
    args = parser.parse_args()

    domains = load_domains(args.input)
    if not domains:
        print("No domains found in input CSV.", file=sys.stderr)
        return 2

    results = [analyze_domain(item, args.check_smtp) for item in domains]
    if args.format == "json":
        output = json.dumps({"generated_at": datetime.now(timezone.utc).isoformat(), "results": results}, ensure_ascii=False, indent=2)
    else:
        output = markdown_report(results)

    if args.output:
        args.output.write_text(output, encoding="utf-8")
    else:
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
