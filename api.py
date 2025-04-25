from flask import Flask, jsonify, request
from flask_cors import CORS
import psutil
import os
import requests
import serial
import time
import json
import re
import threading

app = Flask(__name__)
CORS(app)

# Configuration USB pour ESP32 S3
ESP_PORT = '/dev/ttyUSB0'  # Port USB du Raspberry Pi connecté à l'ESP32 S3
BAUD_RATE = 115200
try:
    ser = serial.Serial(ESP_PORT, BAUD_RATE, timeout=1)
    time.sleep(2)  # Laisse le temps à la connexion de s'établir
    print(f"Connexion USB établie sur {ESP_PORT}")
except Exception as e:
    print(f"Erreur lors de l'initialisation de la connexion USB: {e}")
    ser = None

# Variables pour stocker les dernières données d'orientation
last_orientation = {
    "roll": 0.0,
    "pitch": 0.0,
    "yaw": 0.0,
    "calibration": {
        "system": 0,
        "gyro": 0,
        "accel": 0,
        "mag": 0
    },
    "timestamp": 0
}

# Thread pour lire les données d'orientation en continu
def read_serial_data():
    if ser is None:
        return
    
    # Pattern pour inclure les données de calibration
    orientation_pattern = re.compile(r'O:(-?\d+\.?\d*),(-?\d+\.?\d*),(-?\d+\.?\d*),(\d+),(\d+),(\d+),(\d+)')
    
    while True:
        try:
            if ser.in_waiting > 0:
                line = ser.readline().decode('utf-8').strip()
                
                # Recherche des données d'orientation
                match = orientation_pattern.match(line)
                if match:
                    roll = float(match.group(1))
                    pitch = float(match.group(2))
                    yaw = float(match.group(3))
                    sys_cal = int(match.group(4))
                    gyro_cal = int(match.group(5))
                    accel_cal = int(match.group(6))
                    mag_cal = int(match.group(7))
                    
                    # Mise à jour des données d'orientation
                    global last_orientation
                    last_orientation = {
                        "roll": roll,
                        "pitch": pitch,
                        "yaw": yaw,
                        "calibration": {
                            "system": sys_cal,
                            "gyro": gyro_cal,
                            "accel": accel_cal,
                            "mag": mag_cal
                        },
                        "timestamp": time.time()
                    }
                    print(f"Orientation mise à jour: roll={roll}, pitch={pitch}, yaw={yaw}, cal={sys_cal}/{gyro_cal}/{accel_cal}/{mag_cal}")
        except Exception as e:
            print(f"Erreur lors de la lecture des données série: {e}")
        
        time.sleep(0.01)  # Petit délai pour éviter de surcharger le CPU

# Démarrage du thread de lecture série
serial_thread = threading.Thread(target=read_serial_data, daemon=True)
serial_thread.start()

@app.route('/api/test', methods=['GET'])
def test_api():
    return jsonify({'message': 'API is working'})

@app.route('/api/system/info', methods=['GET'])
def get_system_info():
    cpu_temperature = os.popen("vcgencmd measure_temp").readline().replace("temp=","").replace("'C\\n","")
    ram_usage = psutil.virtual_memory().percent
    load_system = psutil.getloadavg()[0]
    disk_space = psutil.disk_usage('/').percent
    
    return jsonify({
        'cpu_temperature': cpu_temperature,
        'ram_usage': ram_usage,
        'load_system': load_system,
        'disk_space': disk_space
    })

@app.route('/api/camera/status')
def camera_status():
    try:
        response = requests.get('http://localhost:8080/?action=stream', stream=True, timeout=5)
        response.raise_for_status()  # Lève une exception si le code HTTP n'est pas 200 OK
        #On verifie que le content type est bien celui attendu.
        if 'multipart/x-mixed-replace' in response.headers['Content-Type']:
            return jsonify({'status': 'OK', 'message': 'Stream is available'})
        else:
            return jsonify({'status': 'Error', 'message': 'Unexpected content type'}), 500

    except requests.exceptions.RequestException as e:
        return jsonify({'status': 'Error', 'message': f'Stream unavailable: {e}'}), 500

@app.route('/api/motors/control', methods=['POST'])
def control_motors():
    if ser is None:
        return jsonify({"status": "error", "message": "Connexion USB non disponible"}), 500
    
    try:
        data = request.json
        # Validation des valeurs PWM (1000-2000 typique pour ESC)
        motor_values = []
        
        # Récupération des valeurs pour les 8 moteurs
        for i in range(1, 9):
            motor_key = f'm{i}'
            motor_value = max(1000, min(2000, int(data.get(motor_key, 1000))))
            motor_values.append(motor_value)
        
        # Format de commande : "M1:1500;M2:1500;M3:1500;...M8:1500;\n"
        command = ""
        for i, value in enumerate(motor_values, 1):
            command += f"M{i}:{value};"
        command += "\n"
        
        ser.write(command.encode())
        
        # Attente de confirmation (optionnel)
        try:
            response = ser.readline().decode().strip()
            timeout_start = time.time()
            while not response.startswith("ACK:") and (time.time() - timeout_start) < 1.0:
                response = ser.readline().decode().strip()
        except Exception as e:
            response = f"Erreur lors de la lecture de la confirmation: {e}"
        
        return jsonify({
            "status": "success", 
            "command": command,
            "response": response,
            "motors": motor_values
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/orientation', methods=['GET'])
def get_orientation():
    """
    Renvoie les dernières données d'orientation du capteur IMU
    """
    global last_orientation
    
    # Vérifier si les données sont récentes (moins de 5 secondes)
    if time.time() - last_orientation["timestamp"] > 5:
        return jsonify({
            "status": "warning",
            "message": "Les données d'orientation peuvent être obsolètes",
            "data": last_orientation
        })
    
    return jsonify({
        "status": "success",
        "data": last_orientation
    })

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
