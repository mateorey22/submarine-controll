from flask import Flask, jsonify, request
from flask_cors import CORS
import psutil
import os
import requests
import serial
import time
import re
import threading
import json

app = Flask(__name__)
CORS(app)

# --- CONFIGURATION ---
ESP_PORT = '/dev/ttyACM0'
BAUD_RATE = 115200

# --- VARIABLES GLOBALES ---
ser = None
latest_sensor_data = {
    'orientation': {'roll': 0.0, 'pitch': 0.0, 'yaw': 0.0, 'calibration': {'system': 0, 'gyro': 0, 'accel': 0, 'mag': 0}},
    'depth': 0.0,
    'temperature': 20.0,
    'timestamp': time.time()
}

# --- GESTION DE LA CONNEXION SÉRIE ROBUSTE ---
def get_serial_connection():
    """Tente d'obtenir une connexion série active, se reconnecte si nécessaire."""
    global ser
    if ser and ser.is_open:
        return ser
    if ser:
        try:
            ser.close()
        except Exception:
            pass
    try:
        ser = serial.Serial(ESP_PORT, BAUD_RATE, timeout=1)
        time.sleep(2)
        print(f"NOUVELLE connexion USB établie sur {ESP_PORT}")
        return ser
    except serial.SerialException as e:
        print(f"AVERTISSEMENT: Connexion à {ESP_PORT} impossible. Erreur: {e}")
        ser = None
        return None

def send_serial_command(command_str):
    """Fonction sécurisée pour envoyer une commande."""
    local_ser = get_serial_connection()
    if not local_ser:
        return False
    try:
        local_ser.write(command_str.encode())
        return True
    except Exception as e:
        print(f"Erreur d'écriture série: {e}. Invalidation de la connexion.")
        global ser
        ser = None
        return False

# --- ROUTES DE L'API ---

@app.route('/api/test', methods=['GET'])
def test_api():
    return jsonify({'message': 'Enhanced Submarine API is working'})

@app.route('/api/system/info', methods=['GET'])
def get_system_info():
    try:
        cpu_temp_str = os.popen("vcgencmd measure_temp").readline()
        cpu_temperature = cpu_temp_str.replace("temp=","").replace("'C\\n","").strip()
    except Exception:
        cpu_temperature = "N/A"
    return jsonify({
        'cpu_temperature': cpu_temperature,
        'ram_usage': psutil.virtual_memory().percent,
        'load_system': psutil.getloadavg()[0],
        'disk_space': psutil.disk_usage('/').percent
    })

@app.route('/api/camera/status')
def camera_status():
    try:
        response = requests.get('http://localhost:8080/?action=stream', stream=True, timeout=2)
        response.raise_for_status()
        return jsonify({'status': 'OK', 'message': 'Stream is available'})
    except requests.exceptions.RequestException:
        return jsonify({'status': 'Error', 'message': 'Stream unavailable'}), 503

@app.route('/api/motors/control', methods=['POST'])
def control_motors():
    data = request.json
    motor_values = [max(1000, min(2000, int(data.get(f'm{i}', 1000)))) for i in range(1, 9)]
    command = "".join([f"M{i}:{v};" for i, v in enumerate(motor_values, 1)]) + "\n"
    if send_serial_command(command):
        # On ne lit pas de réponse ici pour garder la commande rapide
        return jsonify({"status": "success", "command_sent": command.strip()})
    else:
        return jsonify({"status": "error", "message": "ESP32 non disponible"}), 503

@app.route('/api/control/high_level', methods=['POST'])
def high_level_control():
    data = request.json
    commands_to_send = []
    if 'forward_thrust' in data: commands_to_send.append(f"CMD:FORWARD,VAL:{float(data['forward_thrust'])}\n")
    if 'strafe_thrust' in data: commands_to_send.append(f"CMD:STRAFE,VAL:{float(data['strafe_thrust'])}\n")
    if 'vertical_thrust' in data: commands_to_send.append(f"CMD:VERTICAL,VAL:{float(data['vertical_thrust'])}\n")
    if 'yaw_rate' in data: commands_to_send.append(f"CMD:YAW_RATE,VAL:{float(data['yaw_rate'])}\n")
    if 'target_pitch' in data: commands_to_send.append(f"TARGET:PITCH,VAL:{float(data['target_pitch'])}\n")
    if 'target_roll' in data: commands_to_send.append(f"TARGET:ROLL,VAL:{float(data['target_roll'])}\n")
    if 'target_yaw' in data: commands_to_send.append(f"TARGET:YAW,VAL:{float(data['target_yaw'])}\n")
    
    success_count = sum(1 for cmd in commands_to_send if send_serial_command(cmd))
    
    if success_count > 0:
        # Pas besoin de lire la réponse pour chaque commande pour ne pas ralentir
        return jsonify({"status": "success", "commands_sent": success_count})
    else:
        return jsonify({"status": "error", "message": "ESP32 non disponible"}), 503

@app.route('/api/led/control', methods=['POST'])
def control_led():
    brightness = max(0, min(100, int(request.json.get('brightness', 0))))
    command = f"LED:{brightness};\n"
    if send_serial_command(command):
        return jsonify({"status": "success", "brightness_set": brightness})
    else:
        return jsonify({"status": "error", "message": "ESP32 non disponible"}), 503

def parse_extended_sensor_data(response):
    global latest_sensor_data
    try:
        orientation_match = re.search(r'O:([\d.-]+),([\d.-]+),([\d.-]+),(\d+),(\d+),(\d+),(\d+)', response)
        if orientation_match:
            latest_sensor_data['orientation'] = {
                'roll': float(orientation_match.group(1)), 'pitch': float(orientation_match.group(2)), 'yaw': float(orientation_match.group(3)),
                'calibration': {'system': int(orientation_match.group(4)), 'gyro': int(orientation_match.group(5)), 'accel': int(orientation_match.group(6)), 'mag': int(orientation_match.group(7))}
            }
        
        depth_match = re.search(r'D:([\d.-]+)', response)
        if depth_match: latest_sensor_data['depth'] = float(depth_match.group(1))
        
        temp_match = re.search(r'T:([\d.-]+)', response)
        if temp_match: latest_sensor_data['temperature'] = float(temp_match.group(1))
        
        latest_sensor_data['timestamp'] = time.time()
        return True
    except (IndexError, ValueError) as e:
        print(f"Erreur de parsing des données '{response}': {e}")
        return False

@app.route('/api/telemetry', methods=['GET'])
def get_telemetry():
    local_ser = get_serial_connection()
    if local_ser:
        try:
            local_ser.write(b"GET_ORIENTATION\n")
            response = local_ser.readline().decode().strip()
            if response:
                parse_extended_sensor_data(response)
        except Exception as e:
            print(f"Erreur de lecture télémétrie: {e}")
            global ser
            ser = None
    return jsonify({"status": "success", "data": latest_sensor_data})

@app.route('/api/stabilization/toggle', methods=['POST'])
def toggle_stabilization():
    enabled = request.json.get('enabled', True)
    command = f"STABILIZE:{1 if enabled else 0}\n"
    if send_serial_command(command):
        return jsonify({"status": "success", "stabilization_enabled": enabled})
    else:
        return jsonify({"status": "error", "message": "Failed to send stabilization command"}), 503

@app.route('/api/serial/test', methods=['GET'])
def test_serial():
    if get_serial_connection():
        return jsonify({"connected": True, "port": ESP_PORT, "message": "Connexion à l'ESP32 active."})
    else:
        return jsonify({"connected": False, "port": ESP_PORT, "message": "Échec de la connexion à l'ESP32."})

# --- DÉMARRAGE DE L'APPLICATION ---
if __name__ == '__main__':
    print("Démarrage de l'API Sous-Marin (Version Robuste et Complète)...")
    app.run(debug=False, host='0.0.0.0', port=5000)
