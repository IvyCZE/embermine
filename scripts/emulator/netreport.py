"""Turn the emulator's packet capture into network-hosts.txt (DNS queries and TLS/QUIC server names).

usage: python3 -m scripts.emulator.netreport --pcap FILE --out FILE --session TEXT [--visited FILE]
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from collections import Counter
from pathlib import Path

FILTERS = {
    "DNS queries": ("dns.flags.response == 0", "dns.qry.name"),
    "TLS SNI": ("tls.handshake.type == 1", "tls.handshake.extensions_server_name"),
    "QUIC SNI": ("quic && tls.handshake.type == 1", "tls.handshake.extensions_server_name"),
}


def tshark_values(pcap: Path, display_filter: str, field: str) -> list[str]:
    proc = subprocess.run(
        ["tshark", "-r", str(pcap), "-Y", display_filter, "-T", "fields", "-e", field],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        print(f"tshark failed for {display_filter!r}: {proc.stderr.strip()[:300]}", file=sys.stderr)
    return [line.strip().lower() for line in proc.stdout.splitlines() if line.strip()]


def count_lines(counter: Counter[str]) -> list[str]:
    return [f"{count:6d} {name}" for name, count in sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))]


def render(sections: dict[str, list[str]], session: str, visited: list[str], pcap_bytes: int) -> str:
    out = [
        "# network-hosts.txt",
        f"# Session captured: {session}",
        "# Method: emulator started with -tcpdump, Wi-Fi switched off (svc wifi disable) so that traffic uses the",
        "#   cellular interface that the capture sees. The capture holds all traffic of the emulator (system apps",
        "#   included); host names cannot be attributed to a single app from the packets alone.",
        f"# Packet capture size: {pcap_bytes} bytes",
        "# Pages the script loaded:",
        *[f"#   {url}" for url in visited],
        "",
    ]
    all_hosts: Counter[str] = Counter()
    for title, values in sections.items():
        counter = Counter(v.split(",")[0] for v in values)
        all_hosts.update(counter)
        out.append(f"## {title} (count, name)")
        out.extend(count_lines(counter) or ["(none)"])
        out.append("")
    out.append("## All host names (union of the above, count, name)")
    out.extend(count_lines(all_hosts) or ["(none)"])
    out.append("")
    return "\n".join(out)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pcap", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--session", required=True)
    parser.add_argument("--visited", type=Path)
    args = parser.parse_args()

    visited = args.visited.read_text(encoding="utf-8").split() if args.visited and args.visited.is_file() else []
    size = args.pcap.stat().st_size if args.pcap.is_file() else 0
    sections = {title: tshark_values(args.pcap, f, field) if size else [] for title, (f, field) in FILTERS.items()}
    args.out.write_text(render(sections, args.session, visited, size), encoding="utf-8")
    print(args.out.read_text(encoding="utf-8")[:6000])
    return 0 if size else 1


if __name__ == "__main__":
    sys.exit(main())
