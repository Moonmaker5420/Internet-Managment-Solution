# app.py
from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask import jsonify
import requests
from functools import wraps
import sqlite3
import subprocess
import os
import re
import yaml
import time
from flask import flash

app = Flask(__name__)
app.secret_key = 'qwerty@123'

# Path to Pi-hole's gravity.db
PIHOLE_DB = "/etc/pihole/gravity.db"
WHITELIST_YAML = "/etc/pihole/whitelists.yml"
PIHOLE_API_URL = "http://localhost/api/history"
PIHOLE_API_TOKEN = "gAdkLRiwxT8w/HSKkwt2hG3lF3mRgMjIn4bWeKQC6N0="


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/api/stats')
@login_required
def api_stats():
    return jsonify(get_dashboard_stats())

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        # Replace with secure credential check
        if username == "admin" and password == "whoami":
            session['logged_in'] = True
            return redirect(url_for('dashboard'))
        else:
            flash("❌ Invalid credentials", "danger")
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


def get_dashboard_stats():
    try:
        headers = {
            "Authorization": f"Bearer {PIHOLE_API_TOKEN}",
            "Accept": "application/json"
        }
        response = requests.get(PIHOLE_API_URL, headers=headers, timeout=3)
        if response.ok:
            data = response.json()["history"]

            total_queries = sum(entry["total"] for entry in data)
            total_blocked = sum(entry["blocked"] for entry in data)
            block_percent = (total_blocked / total_queries * 100) if total_queries else 0

            return {
                "total": total_queries,
                "blocked": total_blocked,
                "percent": round(block_percent, 2)
            }
    except Exception as e:
        print("⚠️ Error fetching Pi-hole stats:", e)
    return {"total": 0, "blocked": 0, "percent": 0}


def load_whitelist():
    if not os.path.exists(WHITELIST_YAML):
        return set()
    with open(WHITELIST_YAML, 'r') as f:
        data = yaml.safe_load(f) or {}
        domains = set()
        for entry in data.values():
            items = entry.get("domains", [])
            if isinstance(items, str):
                items = [items]
            domains.update(items)
        return domains

def unlink_domain_from_default(cur, domain_id):
    cur.execute("DELETE FROM domainlist_by_group WHERE domainlist_id = ? AND group_id = 0", (domain_id,))

def extract_base_domain(entry):
    # If it's a URL, extract the domain
    if entry.startswith("http://") or entry.startswith("https://"):
        domain = re.findall(r"https?://([^/]+)", entry)
        if domain:
            return domain[0]
    # If it's already a domain
    return entry.strip()


@app.route('/recent-blocked-domains')
@login_required  # ensure user is authenticated
def recent_blocked_domains():
    try:
        headers = {
            "Authorization": f"Bearer {PIHOLE_API_TOKEN}",
            "Accept": "application/json"
        }
        res = requests.get("http://localhost/api/stats/recent_blocked", headers=headers, timeout=3)
        res.raise_for_status()
        data = res.json()
        return jsonify({"blocked": data.get("blocked", [])})
    except Exception as e:
        print("Error fetching recent blocked domains:", e)
        return jsonify({"blocked": [], "error": str(e)}), 500


@app.route('/')
@login_required
def dashboard():
    conn = sqlite3.connect(PIHOLE_DB)
    cur = conn.cursor()
    # Skip the default group (ID 0)
    cur.execute("SELECT id, name, enabled FROM 'group' WHERE id != 0")
    groups = cur.fetchall()
    conn.close()
    stats = get_dashboard_stats()
    return render_template('dashboard.html', groups=groups, stats=stats)



@app.route('/toggle_group/<int:group_id>')
def toggle_group(group_id):
    conn = sqlite3.connect(PIHOLE_DB)
    cur = conn.cursor()

    cur.execute("SELECT enabled FROM 'group' WHERE id = ?", (group_id,))
    enabled = cur.fetchone()[0]
    new_state = 0 if enabled else 1

    cur.execute("UPDATE 'group' SET enabled = ? WHERE id = ?", (new_state, group_id))
    conn.commit()
    conn.close()
    subprocess.run(["pihole", "reloaddns", "reloadlists"], check=True)
    return redirect(url_for('dashboard'))


@app.route('/blacklist', methods=['GET', 'POST'])
@login_required
def blacklist():
    conn = sqlite3.connect(PIHOLE_DB)
    cur = conn.cursor()

    # Fetch all groups for dropdown
    cur.execute("SELECT id, name FROM 'group' WHERE id != 0")
    groups = cur.fetchall()

    message = ""
    error = ""
    whitelist_set = set(map(extract_base_domain, load_whitelist()))

    if request.method == 'POST':
        group_id = int(request.form['group_id'])
        domains = request.form['domains'].strip().splitlines()

        for entry in domains:
            if not entry:
                continue
            base_domain = extract_base_domain(entry)

            if base_domain in whitelist_set:
                error = f"❌ Domain '{base_domain}' is whitelisted via backend and cannot be blacklisted."
                break

            regex = f"(\\.|^){re.escape(base_domain)}$"
            cur.execute("SELECT id FROM domainlist WHERE domain = ? AND type = 3", (regex,))
            row = cur.fetchone()
            if row:
                domain_id = row[0]
            else:
                cur.execute(
                    "INSERT INTO domainlist (type, domain, enabled, comment) VALUES (3, ?, 1, 'Dashboard')",
                    (regex,)
                )
                domain_id = cur.lastrowid
                conn.commit()

            unlink_domain_from_default(cur, domain_id)

            # Check if already linked to ANY group
            cur.execute(
                "SELECT g.name FROM domainlist_by_group dbg JOIN 'group' g ON dbg.group_id = g.id WHERE dbg.domainlist_id = ?",
                (domain_id,)
            )
            linked_group = cur.fetchone()
            if linked_group:
                error = f"❌ Domain '{base_domain}' is already blacklisted in group: '{linked_group[0]}'. Only one group per domain is allowed."
                break
            cur.execute(
                "INSERT OR IGNORE INTO domainlist_by_group (domainlist_id, group_id) VALUES (?, ?)",
                (domain_id, group_id)
            )

        conn.commit()
        if not error:
            message = "✅ Domains/Links added to blacklist!"
            subprocess.run(["pihole", "reloaddns", "reloadlists"], check=True)
    conn.close()
    return render_template('blacklist.html', groups=groups, message=message, error=error)

@app.route('/blacklist-view', methods=['GET', 'POST'])
@login_required
def blacklist_view():
    conn = sqlite3.connect(PIHOLE_DB)
    cur = conn.cursor()

    # Get all non-default groups
    cur.execute("SELECT id, name FROM 'group' WHERE id != 0")
    groups = cur.fetchall()

    selected_group_id = request.args.get('group_id', type=int)
    domains = []

    if selected_group_id:
        cur.execute("""
            SELECT d.id, d.domain
            FROM domainlist d
            JOIN domainlist_by_group dbg ON d.id = dbg.domainlist_id
            WHERE dbg.group_id = ? AND d.type = 3 AND d.comment = 'Dashboard'
        """, (selected_group_id,))
        domains = cur.fetchall()

    conn.close()
    return render_template('blacklist_view.html', groups=groups, selected_group_id=selected_group_id, domains=domains)

@app.route('/delete-domain/<int:domain_id>/<int:group_id>')
@login_required
def delete_domain(domain_id, group_id):
    conn = sqlite3.connect(PIHOLE_DB)
    cur = conn.cursor()

    # Remove domain from group and delete if no longer used
    cur.execute("DELETE FROM domainlist_by_group WHERE domainlist_id = ? AND group_id = ?", (domain_id, group_id))
    cur.execute("SELECT COUNT(*) FROM domainlist_by_group WHERE domainlist_id = ?", (domain_id,))
    if cur.fetchone()[0] == 0:
        cur.execute("DELETE FROM domainlist WHERE id = ?", (domain_id,))
    conn.commit()
    conn.close()
    subprocess.run(["pihole", "reloaddns", "reloadlists"], check=True)
    return redirect(url_for('blacklist_view', group_id=group_id))


@app.route('/query-log')
def query_log():
    headers = {
        "Authorization": f"Bearer {PIHOLE_API_TOKEN}",
        "Accept": "application/json"
    }
    try:
        res = requests.get("http://localhost/api/queries", headers=headers, timeout=3)
        res.raise_for_status()
        data = res.json().get("queries", [])[:100]
        # Convert timestamps to readable format
        for entry in data:
            entry["time"] = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(entry["time"]))
        return render_template("query_log.html", queries=data)
    except Exception as e:
        print("Query log error:", e)
        return render_template("query_log.html", queries=[], error=str(e))

@app.route('/api/query-log')
def api_query_log():
    headers = {
        "Authorization": f"Bearer {PIHOLE_API_TOKEN}",
        "Accept": "application/json"
    }
    try:
        res = requests.get("http://localhost/api/queries", headers=headers, timeout=3)
        res.raise_for_status()
        data = res.json().get("queries", [])[:100]
        for entry in data:
            entry["time"] = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(entry["time"]))
            entry["is_gravity"] = entry.get("list_id") is not None and entry.get("status") == "GRAVITY"
            entry["is_regex"] = entry.get("list_id") is not None and entry.get("status") == "REGEX"
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    if os.geteuid() != 0:
        print("Run this app as root to access Pi-hole database.")
        exit(1)
    app.run(host='127.0.0.1', port=5000, debug=True)
