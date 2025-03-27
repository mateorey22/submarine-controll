from flask import Flask, jsonify, request
from flask_cors import CORS
import psutil
import os
import requests
import serial
import time
import json

app = Flask(__name__)
CORS(app)

# Configuration USB pour ESP8266
ESP_PORT = '/dev/ttyUSB0'  # Port USB du Raspberry Pi connecté à l'ESP8266
BAUD_RATE = 115200
try:
    ser = serial.Serial(ESP_PORT, BAUD_RATE, timeout=1)
    time.sleep(2)  # Laisse le temps à la connexion de s'établir
    print(f"Connexion USB établie sur {ESP_PORT}")
except Exception as e:
    print(f"Erreur lors de l'initialisation de la connexion USB: {e}")
    ser = None

# Variables pour stocker les données du BNO055
bno055_data = {
    "euler": {"x": 0, "y": 0, "z": 0},
    "gyro": {"x": 0, "y": 0, "z": 0},
    "linear_accel": {"x": 0, "y": 0, "z": 0},
    "mag": {"x": 0, "y": 0, "z": 0},
    "accel": {"x": 0, "y": 0, "z": 0},
    "gravity": {"x": 0, "y": 0, "z": 0},
    "quat": {"w": 0, "x": 0, "y": 0, "z": 0},
    "temp": 0,
    "calib": {"sys": 0, "gyro": 0, "accel": 0, "mag": 0}
}

# Thread pour lire les données du BNO055
import threading
import re

def read_serial_data():
    if ser is None:
        return
    
    while True:
        try:
            line = ser.readline().decode('utf-8', errors='replace').strip()
            print(f"Données série reçues: {line}")  # Debug: afficher toutes les données reçues
            
            if line.startswith("BNO055:"):
                # Extraire les données JSON
                json_str = line[7:]  # Supprimer le préfixe "BNO055:"
                print(f"Données BNO055 extraites: {json_str}")  # Debug
                
                try:
                    data = json.loads(json_str)
                    global bno055_data
                    bno055_data = data
                    print("Données BNO055 mises à jour avec succès")  # Debug
                except json.JSONDecodeError as e:
                    print(f"Erreur de décodage JSON: {e}")
                    print(f"Données reçues: {json_str}")
                    
                    # Tentative de correction des données JSON malformées
                    try:
                        # Parfois, les données peuvent être tronquées ou mal formatées
                        # Essayons de corriger les accolades manquantes
                        if not json_str.endswith("}"):
                            json_str += "}"
                        if json_str.count("{") > json_str.count("}"):
                            json_str += "}"
                        
                        data = json.loads(json_str)
                        global bno055_data
                        bno055_data = data
                        print("Données BNO055 corrigées et mises à jour")  # Debug
                    except:
                        print("Impossible de corriger les données JSON")
        except Exception as e:
            print(f"Erreur lors de la lecture des données série: {e}")
        
        time.sleep(0.01)  # Petit délai pour éviter de surcharger le CPU

# Démarrer le thread de lecture des données série
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
        m1 = max(1000, min(2000, int(data.get('m1', 1000))))
        m2 = max(1000, min(2000, int(data.get('m2', 1000))))
        
        # Format de commande : "M1:1500;M2:1500;\n"
        command = f"M1:{m1};M2:{m2};\n"
        ser.write(command.encode())
        
        # Attente de confirmation (optionnel)
        response = ser.readline().decode().strip()
        
        return jsonify({
            "status": "success", 
            "command": command,
            "response": response
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/bno055', methods=['GET'])
def get_bno055_data():
    # Ajouter un timestamp pour indiquer quand les données ont été récupérées
    response_data = bno055_data.copy()
    response_data['timestamp'] = time.time()
    return jsonify(response_data)

@app.route('/api/bno055/status', methods=['GET'])
def get_bno055_status():
    # Endpoint pour vérifier si les données du BNO055 sont disponibles
    if bno055_data['euler']['x'] == 0 and bno055_data['euler']['y'] == 0 and bno055_data['euler']['z'] == 0:
        # Si toutes les valeurs sont à zéro, il est probable que les données n'ont pas été mises à jour
        return jsonify({
            'status': 'error',
            'message': 'Aucune donnée valide du BNO055 n\'a été reçue',
            'data_available': False
        })
    else:
        return jsonify({
            'status': 'ok',
            'message': 'Données BNO055 disponibles',
            'data_available': True,
            'calibration': bno055_data['calib']
        })

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
