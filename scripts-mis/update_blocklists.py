#!/usr/bin/env python3
import os
import sqlite3
import yaml
import re
import subprocess

PIHOLE_DB = "/etc/pihole/gravity.db"
BLACKLIST_YAML = "/etc/pihole/blacklists.yml"
WHITELIST_YAML = "/etc/pihole/whitelists.yml"
LOG_FILE = "/var/log/pihole-blacklist-sync.log"

def log(msg):
    print(f"[+] {msg}")
    with open(LOG_FILE, "a") as f:
        f.write(f"[+] {msg}\n")

def load_yaml(file_path):
    if not os.path.exists(file_path):
        return {}
    with open(file_path, "r") as f:
        return yaml.safe_load(f) or {}

def connect_db():
    return sqlite3.connect(PIHOLE_DB)

def get_or_create_group(conn, group_name):
    cur = conn.cursor()
    cur.execute("SELECT id FROM 'group' WHERE name = ?", (group_name,))
    row = cur.fetchone()
    if row:
        return row[0]
    cur.execute("INSERT INTO 'group' (enabled, name) VALUES (1, ?)", (group_name,))
    conn.commit()
    return cur.lastrowid

def get_or_create_adlist(conn, url, comment):
    cur = conn.cursor()
    cur.execute("SELECT id FROM adlist WHERE address = ?", (url,))
    row = cur.fetchone()
    if row:
        return row[0]
    cur.execute(
        "INSERT INTO adlist (enabled, address, comment) VALUES (1, ?, ?)",
        (url, comment),
    )
    conn.commit()
    return cur.lastrowid

def unlink_adlist_from_default(conn, adlist_id):
    cur = conn.cursor()
    cur.execute("DELETE FROM adlist_by_group WHERE adlist_id = ? AND group_id = 0", (adlist_id,))
    conn.commit()

def link_adlist_to_group(conn, adlist_id, group_id):
    unlink_adlist_from_default(conn, adlist_id)
    cur = conn.cursor()
    cur.execute(
        "SELECT 1 FROM adlist_by_group WHERE adlist_id = ? AND group_id = ?",
        (adlist_id, group_id),
    )
    if not cur.fetchone():
        cur.execute(
            "INSERT INTO adlist_by_group (adlist_id, group_id) VALUES (?, ?)",
            (adlist_id, group_id),
        )
        conn.commit()

def unlink_domain_from_default(conn, domain_id):
    cur = conn.cursor()
    cur.execute("DELETE FROM domainlist_by_group WHERE domainlist_id = ? AND group_id = 0", (domain_id,))
    conn.commit()

def add_domains_to_group(conn, domains, group_id, whitelist_set):
    cur = conn.cursor()
    added = []
    for domain in domains:
        if domain in whitelist_set:
            log(f"Skipped blacklisting '{domain}' (found in whitelist)")
            continue

        regex_domain = fr"(\.|^){re.escape(domain)}$"
        cur.execute(
            "SELECT id FROM domainlist WHERE domain = ? AND type = 3", (regex_domain,)
        )
        row = cur.fetchone()
        if row:
            domain_id = row[0]
            log(f"Domain already exists: {regex_domain}")
        else:
            cur.execute(
                "INSERT INTO domainlist (type, domain, enabled, comment) VALUES (3, ?, 1, 'Added by script')",
                (regex_domain,),
            )
            conn.commit()
            domain_id = cur.lastrowid
            log(f"Added new domain: {regex_domain}")

        unlink_domain_from_default(conn, domain_id)

        cur.execute(
            "SELECT 1 FROM domainlist_by_group WHERE domainlist_id = ? AND group_id = ?",
            (domain_id, group_id),
        )
        if not cur.fetchone():
            cur.execute(
                "INSERT INTO domainlist_by_group (domainlist_id, group_id) VALUES (?, ?)",
                (domain_id, group_id),
            )
            conn.commit()
        added.append(regex_domain)
    return added

def remove_unlisted_domains(conn, group_id, current_domains):
    cur = conn.cursor()
    cur.execute("""
        SELECT d.id, d.domain FROM domainlist d
        JOIN domainlist_by_group dbg ON d.id = dbg.domainlist_id
        WHERE dbg.group_id = ? AND d.type = 3 AND d.comment = 'Added by script'
    """, (group_id,))
    rows = cur.fetchall()

    for domain_id, domain in rows:
        if domain not in current_domains:
            cur.execute("DELETE FROM domainlist_by_group WHERE domainlist_id = ?", (domain_id,))
            cur.execute("DELETE FROM domainlist WHERE id = ?", (domain_id,))
            conn.commit()
            log(f"Removed obsolete domain: {domain}")

def run_pihole_gravity():
    log("Running 'pihole -g' to apply changes...")
    try:
        subprocess.run(["pihole", "-g"], check=True)
        log("Gravity update complete.")
    except subprocess.CalledProcessError as e:
        log(f"Error running 'pihole -g': {e}")

def collect_whitelist_domains(whitelist_data):
    domains = set()
    for entry in whitelist_data.values():
        items = entry.get("domains", [])
        if isinstance(items, str):
            items = [items]
        domains.update(items)
    return domains

def main():
    if os.geteuid() != 0:
        print("This script must be run as root.")
        return

    log("Starting Pi-hole blacklist sync...")

    conn = connect_db()
    blacklist_data = load_yaml(BLACKLIST_YAML)
    whitelist_data = load_yaml(WHITELIST_YAML)
    whitelist_set = collect_whitelist_domains(whitelist_data)

    for key, entry in blacklist_data.items():
        group_name = entry.get("name", key)
        group_id = get_or_create_group(conn, group_name)

        urls = entry.get("url", [])
        if isinstance(urls, str):
            urls = [urls]

        for url in urls:
            if url:
                adlist_id = get_or_create_adlist(conn, url, group_name)
                link_adlist_to_group(conn, adlist_id, group_id)

        domains = entry.get("domains", [])
        added_domains = []
        if domains:
            added_domains = add_domains_to_group(conn, domains, group_id, whitelist_set)

        remove_unlisted_domains(conn, group_id, added_domains)

    conn.close()
    run_pihole_gravity()
    log("Sync complete.")

if __name__ == "__main__":
    main()