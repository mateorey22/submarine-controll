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
ESP_PORT = '/dev/ttyACM0'  # Port USB correct
BAUD_RATE = 115200
ser = None  # Initialiser à None

# Fonction pour établir la connexion série
def init_serial_connection():
    global ser
    try:
        if ser is not None and ser.is_open:
            ser.close()
        
        ser = serial.Serial(ESP_PORT, BAUD_RATE, timeout=1)
        time.sleep(2)  # Laisse le temps à la connexion de s'établir
        print(f"Connexion USB établie sur {ESP_PORT}")
        return True
    except Exception as e:
        print(f"Erreur lors de l'initialisation de la connexion USB: {e}")
        ser = None
        return False

# Essayer d'initialiser la connexion série au démarrage
init_serial_connection()

@app.route('/api/test', methods=['GET'])
def test_api():
    return jsonify({'message': 'API is working'})

@app.route('/api/system/info', methods=['GET'])
def get_system_info():
    try:
        cpu_temperature_raw = os.popen("vcgencmd measure_temp").readline()
        cpu_temperature = cpu_temperature_raw.replace("temp=","").replace("'C\\n","").strip()
        if not cpu_temperature:
             cpu_temperature = "N/A"
    except Exception:
        cpu_temperature = "N/A"
        
    try:
        ram_usage = psutil.virtual_memory().percent
        load_system = psutil.getloadavg()[0]
        disk_space = psutil.disk_usage('/').percent
    except Exception as e:
        print(f"Erreur psutil: {e}")
        ram_usage = "N/A"
        load_system = "N/A"
        disk_space = "N/A"
        
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
        response.raise_for_status()
        if 'multipart/x-mixed-replace' in response.headers.get('Content-Type', ''):
            return jsonify({'status': 'OK', 'message': 'Stream is available'})
        else:
            return jsonify({'status': 'Error', 'message': 'Unexpected content type'}), 500

    except requests.exceptions.RequestException as e:
        print(f"Erreur camera status: {e}")
        return jsonify({'status': 'Error', 'message': f'Stream unavailable: {e}'}), 500
    except Exception as e:
        print(f"Erreur inattendue camera status: {e}")
        return jsonify({'status': 'Error', 'message': f'Unexpected error: {e}'}), 500

@app.route('/api/motors/control', methods=['POST'])
def control_motors():
    if ser is None or not ser.is_open:
        if not init_serial_connection():
            return jsonify({"status": "error", "message": "Connexion USB non disponible"}), 500
        
    try:
        data = request.json
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
        print(f"Envoi commande moteurs: {command.strip()}")
        ser.write(command.encode())
        
        # Attendre une réponse simple
        response = "No response"  # Valeur par défaut
        try:
            original_timeout = ser.timeout
            ser.timeout = 0.5 
            response = ser.readline().decode('utf-8', errors='replace').strip()
            ser.timeout = original_timeout
            print(f"Réponse moteurs: {response}")
        except Exception as e:
            print(f"Erreur lors de la lecture de la réponse moteur: {e}")
            response = f"Erreur lecture: {e}"
        
        return jsonify({
            "status": "success", 
            "command_sent": command.strip(),
            "response_from_esp32": response
        })
    except Exception as e:
        print(f"Erreur dans /api/motors/control: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/led/control', methods=['POST'])
def control_led():
    if ser is None or not ser.is_open:
        if not init_serial_connection():
            return jsonify({"status": "error", "message": "Connexion USB non disponible"}), 500
        
    try:
        data = request.json
        # Validation de la valeur de luminosité (0-100)
        brightness = max(0, min(100, int(data.get('brightness', 0))))
        
        # Format de commande : "LED:50;\n"
        command = f"LED:{brightness};\n"
        
        # Envoyer la commande
        print(f"Envoi commande LED: {command.strip()}")
        ser.write(command.encode())
        
        # Attendre une réponse simple
        response = "No response"  # Valeur par défaut
        try:
            original_timeout = ser.timeout
            ser.timeout = 0.5 
            response = ser.readline().decode('utf-8', errors='replace').strip()
            ser.timeout = original_timeout
            print(f"Réponse LED: {response}")
        except Exception as e:
            print(f"Erreur lors de la lecture de la réponse LED: {e}")
            response = f"Erreur lecture: {e}"
        
        return jsonify({
            "status": "success", 
            "command_sent": command.strip(),
            "response_from_esp32": response,
            "brightness_set": brightness
        })
    except Exception as e:
        print(f"Erreur dans /api/led/control: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/orientation', methods=['GET'])
def get_orientation():
    """ Renvoie les données d'orientation du capteur IMU (via ESP32) """
    if ser is None or not ser.is_open:
        if not init_serial_connection():
            return jsonify({"status": "error", "message": "Connexion USB non disponible"}), 500
        
    try:
        command_to_esp = b"GET_ORIENTATION\n"
        print(f"Envoi commande orientation: {command_to_esp.strip()}")
        ser.reset_input_buffer()  # Vider le buffer d'entrée avant d'envoyer
        ser.write(command_to_esp)
        
        # Attendre la réponse
        original_timeout = ser.timeout
        ser.timeout = 1.0 
        response = ser.readline().decode('utf-8', errors='replace').strip()
        ser.timeout = original_timeout
        print(f"Réponse orientation: {response}")
        
        # Analyser la réponse avec une expression régulière
        orientation_pattern = re.compile(r'O:(-?\d+\.?\d*),(-?\d+\.?\d*),(-?\d+\.?\d*),(\d+),(\d+),(\d+),(\d+)')
        match = orientation_pattern.match(response)
        
        if match:
            orientation_data = {
                "roll": float(match.group(1)),
                "pitch": float(match.group(2)),
                "yaw": float(match.group(3)),
                "calibration": {
                    "system": int(match.group(4)),
                    "gyro": int(match.group(5)),
                    "accel": int(match.group(6)),
                    "mag": int(match.group(7))
                },
                "timestamp": time.time()
            }
            return jsonify({"status": "success", "data": orientation_data})
        else:
            return jsonify({
                "status": "error",
                "message": "Format de réponse d'orientation invalide reçu de l'ESP32.",
                "response_from_esp32": response or "No response"
            }), 500
            
    except serial.SerialTimeoutException:
        print("Timeout lors de l'attente de la réponse orientation.")
        return jsonify({"status": "error", "message": "Timeout: No response from ESP32 for orientation data."}), 500
    except Exception as e:
        print(f"Erreur dans /api/orientation: {e}")
        # Tentative de réinitialisation de la connexion
        try:
            init_serial_connection()
        except:
            pass
        return jsonify({
            "status": "error",
            "message": f"Erreur lors de la lecture des données d'orientation: {e}"
        }), 500

@app.route('/api/depth', methods=['GET'])
def get_depth_data():
    """ Renvoie les données de profondeur du capteur GY-MS5837 (via ESP32) """
    if ser is None or not ser.is_open:
        if not init_serial_connection():
            return jsonify({"status": "error", "message": "Connexion USB non disponible"}), 500
    
    try:
        command_to_esp = b"GET_DEPTH\n"
        print(f"Envoi commande profondeur: {command_to_esp.strip()}")
        ser.reset_input_buffer()  # Vider le buffer d'entrée avant d'envoyer
        ser.write(command_to_esp)
        
        # Attendre la réponse
        original_timeout = ser.timeout
        ser.timeout = 1.0  # Timeout un peu plus long pour la réponse capteur
        response = ser.readline().decode('utf-8', errors='replace').strip()
        ser.timeout = original_timeout
        print(f"Réponse profondeur: {response}")
        
        # Analyser la réponse avec une expression régulière
        depth_pattern = re.compile(r'D:(-?\d+\.?\d*),(-?\d+\.?\d*)')
        match = depth_pattern.match(response)
        
        if match:
            depth_data = {
                "depth": float(match.group(1)),      # Profondeur en mètres
                "pressure": float(match.group(2)),   # Pression en mbar
                "timestamp": time.time()
            }
            return jsonify({"status": "success", "data": depth_data})
        else:
            return jsonify({
                "status": "error",
                "message": "Format de réponse de profondeur invalide reçu de l'ESP32.",
                "response_from_esp32": response or "No response"
            }), 500
            
    except serial.SerialTimeoutException:
        print("Timeout lors de l'attente de la réponse profondeur.")
        return jsonify({"status": "error", "message": "Timeout: No response from ESP32 for depth data."}), 500
    except Exception as e:
        print(f"Erreur dans /api/depth: {e}")
        # Tentative de réinitialisation de la connexion
        try:
            init_serial_connection()
        except:
            pass
        return jsonify({
            "status": "error",
            "message": f"Erreur lors de la lecture des données de profondeur: {e}"
        }), 500

if __name__ == '__main__':
    print("Démarrage de l'API Flask...")
    app.run(debug=True, host='0.0.0.0', port=5000)
