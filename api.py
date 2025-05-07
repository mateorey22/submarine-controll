from flask import Flask, jsonify, request
from flask_cors import CORS
import psutil
import os
import requests
import serial
import time
import re

app = Flask(__name__)
CORS(app)

# Configuration USB pour ESP32 S3
ESP_PORT = '/dev/ttyACM1' # Port USB du Raspberry Pi connecté à l'ESP32 S3
BAUD_RATE = 115200
try:
    ser = serial.Serial(ESP_PORT, BAUD_RATE, timeout=1)
    time.sleep(2)  # Laisse le temps à la connexion de s'établir
    print(f"Connexion USB établie sur {ESP_PORT}")
except Exception as e:
    print(f"Erreur lors de l'initialisation de la connexion USB: {e}")
    ser = None

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
        
        # Envoyer la commande
        ser.write(command.encode())
        
        # Attendre une réponse simple
        try:
            response = ser.readline().decode().strip()
        except Exception as e:
            response = f"Erreur: {e}"
        
        return jsonify({
            "status": "success", 
            "command": command,
            "response": response
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/led/control', methods=['POST'])
def control_led():
    if ser is None:
        return jsonify({"status": "error", "message": "Connexion USB non disponible"}), 500
    
    try:
        data = request.json
        # Validation de la valeur de luminosité (0-100)
        brightness = max(0, min(100, int(data.get('brightness', 0))))
        
        # Format de commande : "LED:50;\n"
        command = f"LED:{brightness};\n"
        
        # Envoyer la commande
        ser.write(command.encode())
        
        # Attendre une réponse simple
        try:
            response = ser.readline().decode().strip()
        except Exception as e:
            response = f"Erreur: {e}"
        
        return jsonify({
            "status": "success", 
            "command": command,
            "response": response,
            "brightness": brightness
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/orientation', methods=['GET'])
def get_orientation():
    """
    Renvoie les données d'orientation du capteur IMU
    """
    if ser is None:
        return jsonify({"status": "error", "message": "Connexion USB non disponible"}), 500
    
    try:
        # Envoyer une commande pour demander les données d'orientation
        ser.write(b"GET_ORIENTATION\n")
        
        # Attendre la réponse
        response = ser.readline().decode().strip()
        
        # Analyser la réponse avec une expression régulière
        orientation_pattern = re.compile(r'O:(-?\d+\.?\d*),(-?\d+\.?\d*),(-?\d+\.?\d*),(\d+),(\d+),(\d+),(\d+)')
        match = orientation_pattern.match(response)
        
        if match:
            roll = float(match.group(1))
            pitch = float(match.group(2))
            yaw = float(match.group(3))
            sys_cal = int(match.group(4))
            gyro_cal = int(match.group(5))
            accel_cal = int(match.group(6))
            mag_cal = int(match.group(7))
            
            orientation_data = {
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
            
            return jsonify({
                "status": "success",
                "data": orientation_data
            })
        else:
            return jsonify({
                "status": "error",
                "message": "Format de réponse invalide",
                "response": response
            }), 500
            
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": f"Erreur lors de la lecture des données d'orientation: {e}"
        }), 500

@app.route('/api/depth', methods=['GET'])
def get_depth_data():
    """
    Renvoie les données de profondeur du capteur GY-MS5837
    """
    if ser is None:
        return jsonify({"status": "error", "message": "Connexion USB non disponible"}), 500
    
    try:
        # Envoyer une commande pour demander les données de profondeur
        ser.write(b"GET_DEPTH\n")
        
        # Attendre la réponse
        response = ser.readline().decode().strip()
        
        # Analyser la réponse avec une expression régulière
        # Format attendu: "D:depth,pressure"
        depth_pattern = re.compile(r'D:(-?\d+\.?\d*),(-?\d+\.?\d*)')
        match = depth_pattern.match(response)
        
        if match:
            depth = float(match.group(1))      # Profondeur en mètres
            pressure = float(match.group(2))   # Pression en mbar
            
            return jsonify({
                "status": "success",
                "depth": depth,
                "pressure": pressure,
                "timestamp": time.time()
            })
        else:
            return jsonify({
                "status": "error",
                "message": "Format de réponse invalide",
                "response": response
            }), 500
            
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": f"Erreur lors de la lecture des données de profondeur: {e}"
        }), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
