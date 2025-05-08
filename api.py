# Code basé sur la version fonctionnelle fournie par l'utilisateur,
# avec ajout de l'endpoint /api/depth et correction du port série.

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

# Configuration USB pour ESP32 S3 - Corrigé selon la demande de l'utilisateur
ESP_PORT = '/dev/ttyACM0' # Port USB correct
BAUD_RATE = 115200
ser = None # Initialiser à None

# Essayer d'initialiser la connexion série au démarrage (comme dans la version fonctionnelle)
try:
    ser = serial.Serial(ESP_PORT, BAUD_RATE, timeout=1)
    time.sleep(2)  # Laisse le temps à la connexion de s'établir
    print(f"Connexion USB établie sur {ESP_PORT}")
except Exception as e:
    print(f"Erreur lors de l'initialisation de la connexion USB: {e}")
    ser = None # S'assurer que ser est None si l'ouverture échoue

@app.route('/api/test', methods=['GET'])
def test_api():
    # Fonction originale
    return jsonify({'message': 'API is working'})

@app.route('/api/system/info', methods=['GET'])
def get_system_info():
    # Fonction originale
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
    # Fonction originale
    try:
        response = requests.get('http://localhost:8080/?action=stream', stream=True, timeout=5)
        response.raise_for_status()  # Lève une exception si le code HTTP n'est pas 200 OK
        #On verifie que le content type est bien celui attendu.
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
    # Fonction originale, avec la vérification initiale de 'ser'
    if ser is None:
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
        response = "No response" # Valeur par défaut
        try:
            # Mettre un timeout plus court pour la lecture de l'ACK pour éviter de bloquer
            original_timeout = ser.timeout
            ser.timeout = 0.5 
            response = ser.readline().decode('utf-8').strip()
            ser.timeout = original_timeout # Remettre le timeout original
            print(f"Réponse moteurs: {response}")
        except Exception as e:
            print(f"Erreur lors de la lecture de la réponse moteur: {e}")
            response = f"Erreur lecture: {e}" # Ou garder "No response"
        
        # Retourner le statut success même si la réponse n'est pas parfaite, comme dans l'original
        return jsonify({
            "status": "success", 
            "command_sent": command.strip(),
            "response_from_esp32": response
        })
    except Exception as e:
        print(f"Erreur dans /api/motors/control: {e}")
        # En cas d'erreur ici, on pourrait essayer de gérer la reconnexion
        # mais pour rester fidèle à l'original, on retourne juste l'erreur.
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/led/control', methods=['POST'])
def control_led():
    # Fonction originale, avec la vérification initiale de 'ser'
    if ser is None:
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
        response = "No response" # Valeur par défaut
        try:
            original_timeout = ser.timeout
            ser.timeout = 0.5 
            response = ser.readline().decode('utf-8').strip()
            ser.timeout = original_timeout
            print(f"Réponse LED: {response}")
        except Exception as e:
            print(f"Erreur lors de la lecture de la réponse LED: {e}")
            response = f"Erreur lecture: {e}"
        
        return jsonify({
            "status": "success", 
            "command_sent": command.strip(),
            "response_from_esp32": response,
            "brightness_set": brightness # Renommé pour clarifier vs 'brightness' dans data
        })
    except Exception as e:
        print(f"Erreur dans /api/led/control: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/orientation', methods=['GET'])
def get_orientation():
    """ Renvoie les données d'orientation du capteur IMU (via ESP32) """
    # Fonction originale, avec la vérification initiale de 'ser'
    if ser is None:
        return jsonify({"status": "error", "message": "Connexion USB non disponible"}), 500
        
    try:
        command_to_esp = b"GET_ORIENTATION\n"
        print(f"Envoi commande orientation: {command_to_esp.strip()}")
        ser.write(command_to_esp)
        
        # Attendre la réponse
        # Mettre un timeout un peu plus long car le capteur peut prendre du temps
        original_timeout = ser.timeout
        ser.timeout = 1.0 
        response = ser.readline().decode('utf-8').strip()
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
            # Si le format ne correspond pas, retourner une erreur mais inclure la réponse reçue
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
        # En cas d'erreur ici, la connexion série pourrait être perdue
        global ser
        try: 
            if ser: ser.close()
        except: pass
        ser = None # Invalider la connexion pour forcer une tentative de reconnexion
        return jsonify({
            "status": "error",
            "message": f"Erreur lors de la lecture des données d'orientation: {e}"
        }), 500

# --- NOUVEL ENDPOINT POUR LA PROFONDEUR (AJOUTÉ) ---
@app.route('/api/depth', methods=['GET'])
def get_depth_data():
    """ Renvoie les données de profondeur du capteur GY-MS5837 (via ESP32) """
    if ser is None:
        # Essayer de rouvrir une fois si la connexion a été perdue au démarrage
        global ser
        try:
            print("Tentative de reconnexion série pour profondeur...")
            ser = serial.Serial(ESP_PORT, BAUD_RATE, timeout=1)
            if not ser.is_open: raise serial.SerialException("Impossible de rouvrir le port.")
            print("Reconnexion série réussie.")
        except Exception as e:
            print(f"Échec de la reconnexion série: {e}")
            ser = None
            return jsonify({"status": "error", "message": f"Connexion USB non disponible: {e}"}), 500
    
    try:
        command_to_esp = b"GET_DEPTH\n"
        print(f"Envoi commande profondeur: {command_to_esp.strip()}")
        # Vider le buffer d'entrée avant d'envoyer pour éviter de lire une vieille réponse
        ser.reset_input_buffer() 
        ser.write(command_to_esp)
        
        # Attendre la réponse
        original_timeout = ser.timeout
        ser.timeout = 1.0 # Timeout un peu plus long pour la réponse capteur
        response = ser.readline().decode('utf-8').strip()
        ser.timeout = original_timeout
        print(f"Réponse profondeur: {response}")
        
        # Analyser la réponse avec une expression régulière
        # Format attendu: D:depth,pressure (ex: D:1.23,1024.50)
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
        global ser
        try: 
            if ser: ser.close()
        except: pass
        ser = None
        return jsonify({
            "status": "error",
            "message": f"Erreur lors de la lecture des données de profondeur: {e}"
        }), 500
# --- FIN DE L'ENDPOINT AJOUTÉ ---

if __name__ == '__main__':
    # Lancement original
    print("Démarrage de l'API Flask...")
    app.run(debug=True, host='0.0.0.0', port=5000) 
