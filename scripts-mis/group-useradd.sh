#!/bin/bash

DB="/etc/pihole/gravity.db"
SUBNET="192.168.1.0/24"

CLIENT_COMMENT="All local clients"

# Ensure the Pi-hole database exists
if [ ! -f "$DB" ]; then
    echo "❌ Pi-hole database not found at $DB"
    exit 1
fi

# Get or insert the client (subnet)
CLIENT_ID=$(sqlite3 "$DB" "SELECT id FROM client WHERE ip = '$SUBNET';")
if [ -z "$CLIENT_ID" ]; then
    sqlite3 "$DB" "INSERT INTO client (ip, comment) VALUES ('$SUBNET', '$CLIENT_COMMENT');"
    CLIENT_ID=$(sqlite3 "$DB" "SELECT id FROM client WHERE ip = '$SUBNET';")
    echo "[+] Added new client: $SUBNET (ID: $CLIENT_ID)"
else
    echo "[✓] Client already exists: $SUBNET (ID: $CLIENT_ID)"
fi

# Get all group IDs
GROUP_IDS=$(sqlite3 "$DB" "SELECT id FROM 'group';")

# Track how many were newly added
NEW_LINKS=0

for GROUP_ID in $GROUP_IDS; do
    LINK_EXISTS=$(sqlite3 "$DB" "SELECT 1 FROM client_by_group WHERE client_id = $CLIENT_ID AND group_id = $GROUP_ID LIMIT 1;")
    if [ -z "$LINK_EXISTS" ]; then
        sqlite3 "$DB" "INSERT INTO client_by_group (client_id, group_id) VALUES ($CLIENT_ID, $GROUP_ID);"
        echo "[+] Linked $SUBNET to group ID $GROUP_ID"
        NEW_LINKS=$((NEW_LINKS + 1))
    else
        echo "[✓] $SUBNET already linked to group ID $GROUP_ID"
    fi
done

echo
if [ "$NEW_LINKS" -eq 0 ]; then
    echo "[✓] No new group links were needed. Everything is up to date."
else
    echo "[✔] $NEW_LINKS new group links created for $SUBNET."
fi
pihole -g