from flask import Flask, jsonify, request
from flask_cors import CORS
import psutil
import os
import requests # Gardé si vous avez d'autres usages, sinon non nécessaire pour la communication ESP32 directe
import serial
import time
import re
import threading

app = Flask(__name__)
CORS(app) # Permet les requêtes cross-origin, utile pour le développement web

# Configuration USB pour ESP32
# Adaptez le port si nécessaire (ex: /dev/ttyUSB0, /dev/ttyACM0, etc.)
# Sur Raspberry Pi 3/4/Zero W, /dev/ttyS0 ou /dev/serial0 est souvent le port série matériel GPIO.
# Si l'ESP32 est connecté via un adaptateur USB-Série, ce sera /dev/ttyUSBx ou /dev/ttyACMx.
# Votre code original utilisait /dev/ttyACM1, je le conserve.
ESP_PORT = '/dev/ttyACM0' 
BAUD_RATE = 115200
ser = None # Variable globale pour la connexion série

# Variables globales pour stocker les dernières données des capteurs
latest_orientation_data = {
    "roll": 0.0, "pitch": 0.0, "yaw": 0.0,
    "calibration": {"system": 0, "gyro": 0, "accel": 0, "mag": 0},
    "timestamp": 0
}
latest_depth_data = {
    "depth": 0.0, "pressure": 0.0, "timestamp": 0
}
esp32_status_response = "ESP32_UNKNOWN" # Pour la commande TEST

# Lock pour l'accès concurrentiel à la liaison série si plusieurs requêtes la sollicitent
serial_lock = threading.Lock()

def init_serial_connection():
    global ser
    try:
        ser = serial.Serial(ESP_PORT, BAUD_RATE, timeout=1)
        time.sleep(2)  # Laisse le temps à la connexion de s'établir
        print(f"Connexion USB établie sur {ESP_PORT}")
        # Envoyer une commande de test initiale pour vérifier la connexion
        with serial_lock:
            ser.write(b"TEST\n")
            response = ser.readline().decode().strip()
            print(f"Réponse initiale de l'ESP32 au TEST: {response}")
    except serial.SerialException as e:
        print(f"Erreur critique lors de l'initialisation de la connexion USB: {e}")
        ser = None
    except Exception as e:
        print(f"Autre erreur lors de l'initialisation de la connexion USB: {e}")
        ser = None


# --- Fonctions pour envoyer des commandes et lire les réponses ---
def send_command_to_esp32(command_str):
    """
    Envoie une commande à l'ESP32 et retourne la première ligne de réponse.
    Gère les erreurs de communication série.
    """
    if ser is None or not ser.is_open:
        print("Erreur: Connexion série avec l'ESP32 non disponible.")
        return None # Ou lever une exception

    with serial_lock: # S'assurer qu'un seul thread accède à la liaison série à la fois
        try:
            print(f"Envoi à ESP32: {command_str.strip()}")
            ser.write(command_str.encode())
            # Attendre une réponse spécifique ou un timeout
            # Lire plusieurs lignes si nécessaire, en fonction du protocole ESP32
            response_line = ser.readline().decode('utf-8').strip()
            print(f"Reçu de ESP32: {response_line}")
            return response_line
        except serial.SerialTimeoutException:
            print(f"Timeout lors de l'attente de la réponse pour la commande: {command_str.strip()}")
            return None
        except Exception as e:
            print(f"Erreur de communication série lors de l'envoi/réception: {e}")
            # Tenter de rouvrir le port en cas d'erreur grave
            # global ser
            # try:
            #     if ser: ser.close()
            #     init_serial_connection() # Tenter de réinitialiser
            # except Exception as reinit_e:
            #     print(f"Échec de la réinitialisation de la connexion série: {reinit_e}")
            #     ser = None
            return None


@app.route('/api/test_esp32_connection', methods=['GET'])
def test_esp32_connection_endpoint():
    """Endpoint pour tester explicitement la connexion avec l'ESP32."""
    response = send_command_to_esp32("TEST\n")
    if response and "ESP32_OK" in response:
        return jsonify({'status': 'success', 'message': 'ESP32 connecté et répond.', 'esp32_response': response})
    elif response:
        return jsonify({'status': 'error', 'message': 'ESP32 a répondu mais de manière inattendue.', 'esp32_response': response}), 500
    else:
        return jsonify({'status': 'error', 'message': 'Aucune réponse de l\'ESP32 ou erreur de communication.'}), 500


@app.route('/api/system/info', methods=['GET'])
def get_system_info():
    # Cette fonction reste inchangée par rapport à votre code original
    try:
        cpu_temperature_raw = os.popen("vcgencmd measure_temp").readline()
        cpu_temperature = cpu_temperature_raw.replace("temp=","").replace("'C\n","").strip()
    except Exception:
        cpu_temperature = "N/A" # Pour les systèmes non-Raspberry Pi ou si vcgencmd échoue
        
    ram_usage = psutil.virtual_memory().percent
    # psutil.getloadavg() retourne une moyenne sur 1, 5, et 15 minutes. Prenons la première.
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
    # Cette fonction reste inchangée
    try:
        # Assurez-vous que l'adresse et le port du stream MJPG sont corrects
        response = requests.get('http://localhost:8080/?action=stream', stream=True, timeout=2) # Timeout réduit
        response.raise_for_status()
        if 'multipart/x-mixed-replace' in response.headers.get('Content-Type', ''):
            return jsonify({'status': 'OK', 'message': 'Stream disponible'})
        else:
            return jsonify({'status': 'Error', 'message': 'Type de contenu inattendu du stream'}), 500
    except requests.exceptions.RequestException as e:
        return jsonify({'status': 'Error', 'message': f'Stream indisponible: {e}'}), 500

@app.route('/api/motors/control', methods=['POST'])
def control_motors():
    if ser is None:
        return jsonify({"status": "error", "message": "Connexion USB avec ESP32 non disponible"}), 500
    
    try:
        data = request.json
        motor_values_to_send = []
        command_parts = []
        
        for i in range(1, 9): # Pour 8 moteurs, M1 à M8
            motor_key = f'm{i}'
            # Valeur par défaut 1000 (arrêt) si non fournie, et contrainte entre 1000 et 2000
            motor_value = max(1000, min(2000, int(data.get(motor_key, 1000))))
            command_parts.append(f"M{i}:{motor_value}")
        
        command_to_esp = ";".join(command_parts) + ";\n" # Format: M1:1500;M2:1500;...M8:1500;
        
        esp_response = send_command_to_esp32(command_to_esp)
        
        if esp_response and "MOTORS_OK" in esp_response:
            return jsonify({
                "status": "success", 
                "command_sent": command_to_esp.strip(),
                "response_from_esp32": esp_response
            })
        else:
            return jsonify({
                "status": "error", 
                "message": "Erreur ou réponse inattendue de l'ESP32 pour la commande moteurs.",
                "command_sent": command_to_esp.strip(),
                "response_from_esp32": esp_response or "No response"
            }), 500
            
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/led/control', methods=['POST'])
def control_led():
    if ser is None:
        return jsonify({"status": "error", "message": "Connexion USB avec ESP32 non disponible"}), 500
    
    try:
        data = request.json
        brightness = max(0, min(100, int(data.get('brightness', 0)))) # 0-100%
        command_to_esp = f"LED:{brightness};\n"
        
        esp_response = send_command_to_esp32(command_to_esp)

        if esp_response and "LED_OK" in esp_response:
            return jsonify({
                "status": "success", 
                "command_sent": command_to_esp.strip(),
                "response_from_esp32": esp_response,
                "brightness_set": brightness
            })
        else:
            return jsonify({
                "status": "error", 
                "message": "Erreur ou réponse inattendue de l'ESP32 pour la commande LED.",
                "command_sent": command_to_esp.strip(),
                "response_from_esp32": esp_response or "No response"
            }), 500
            
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/orientation', methods=['GET'])
def get_orientation():
    """ Renvoie les données d'orientation du capteur IMU (via ESP32) """
    if ser is None:
        return jsonify({"status": "error", "message": "Connexion USB non disponible"}), 500
    
    response = send_command_to_esp32("GET_ORIENTATION\n")
    
    if response:
        # Format attendu: O:roll,pitch,yaw,sys_cal,gyro_cal,accel_cal,mag_cal
        orientation_pattern = re.compile(r'O:(-?\d+\.?\d*),(-?\d+\.?\d*),(-?\d+\.?\d*),(\d+),(\d+),(\d+),(\d+)')
        match = orientation_pattern.match(response)
        
        if match:
            global latest_orientation_data
            latest_orientation_data = {
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
            return jsonify({"status": "success", "data": latest_orientation_data})
        else:
            return jsonify({
                "status": "error",
                "message": "Format de réponse d'orientation invalide de l'ESP32.",
                "response_from_esp32": response
            }), 500
    else:
        return jsonify({
            "status": "error",
            "message": "Aucune réponse de l'ESP32 pour les données d'orientation."
        }), 500

@app.route('/api/depth', methods=['GET'])
def get_depth_data():
    """ Renvoie les données de profondeur du capteur GY-MS5837 (via ESP32) """
    if ser is None:
        return jsonify({"status": "error", "message": "Connexion USB non disponible"}), 500
        
    response = send_command_to_esp32("GET_DEPTH\n") # Envoie la commande à l'ESP32
    
    if response:
        # Format attendu: D:depth,pressure (ex: D:1.23,1024.50)
        depth_pattern = re.compile(r'D:(-?\d+\.?\d*),(-?\d+\.?\d*)')
        match = depth_pattern.match(response)
        
        if match:
            global latest_depth_data
            latest_depth_data = {
                "depth": float(match.group(1)),      # Profondeur en mètres
                "pressure": float(match.group(2)),   # Pression en mbar
                "timestamp": time.time()
            }
            return jsonify({"status": "success", "data": latest_depth_data})
        else:
            return jsonify({
                "status": "error",
                "message": "Format de réponse de profondeur invalide de l'ESP32.",
                "response_from_esp32": response
            }), 500
    else:
        return jsonify({
            "status": "error",
            "message": "Aucune réponse de l'ESP32 pour les données de profondeur."
        }), 500

if __name__ == '__main__':
    init_serial_connection() # Initialiser la connexion série au démarrage de Flask
    if ser is None:
        print("AVERTISSEMENT: L'API démarre sans connexion série fonctionnelle à l'ESP32.")
        # Vous pourriez choisir de ne pas démarrer Flask ici si la connexion ESP32 est critique
        # exit(1) 
        
    # Lancer l'application Flask. Utiliser debug=False et threaded=True en production.
    # Pour le développement, debug=True est utile.
    app.run(debug=True, host='0.0.0.0', port=5000, threaded=True)
