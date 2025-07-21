# 🛡️ IMS Pi-hole Dashboard

Building a Dashboard for Group/Category Based Content Filtering for Pi-hole.
---

## 🚀 Features

- 🔐 **Login-protected** Flask interface
- 🎛️ **Group Management** – Enable/disable Pi-hole DNS blocking groups
- 🚫 **Blacklist Domains** with regex support (auto-linked to groups)
- 📋 **View/Delete Blacklist** entries per group
- 📡 **Live Query Log** (auto-refreshing)
- 🧠 **Recent Block Alerting** – Get real-time alerts in the UI for blocked domains
- 🌙 **Dark/Light Mode** theme toggle
- ⚙️ **Fully Docker-ready** frontend reverse proxy via Nginx
- 🔒 **ModSecurity + OWASP CRS** (optional for hardened setups)

---

## 📷 Screenshots

![Alt text](https://github.com/Moonmaker5420/Internet-Managment-Solution/blob/main/images/1.PNG)
![Alt text](https://github.com/Moonmaker5420/Internet-Managment-Solution/blob/main/images/2.PNG)
![Alt text](https://github.com/Moonmaker5420/Internet-Managment-Solution/blob/main/images/5.PNG)

---

## 🧰 Tech Stack

- **Backend**: Python 3 + Flask
- **Frontend**: Bootstrap 5 + JavaScript
- **Database**: Pi-hole’s native `gravity.db` (SQLite)
- **Reverse Proxy**: Nginx (Dockerized)
- **Security**: Optional ModSecurity (OWASP CRS)

---

## 📦 Setup & Installation

### ⚙️ 1. Requirements

- Pi-hole installed locally (access to `/etc/pihole/gravity.db`)
- Python 3.7+
- `pip` + `sqlite3` + `subprocess`
- Optional: Docker + Nginx

---

### 🐍 2. Python Environment

```bash
git clone https://github.com/Moonmaker5420/Internet-Managment-Solution.git
cd pihole-dashboard

python3 -m venv venv
source venv/bin/activate

pip install -r requirements.txt
