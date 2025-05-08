# Ce code est basé sur votre fichier original 'sauvegarde_pression/submarin/submarine/api/api.py'
# avec l'ajout de l'endpoint /api/depth

from flask import Flask, jsonify, request
from flask_cors import CORS
import psutil
import os
import requests # Gardé car utilisé dans /api/camera/status
import serial
import time
import re

app = Flask(__name__)
CORS(app)

# Configuration USB pour ESP32 S3 - Reprise de votre configuration originale
ESP_PORT = '/dev/ttyACM0' # Port USB du Raspberry Pi connecté à l'ESP32 S3
BAUD_RATE = 115200
ser = None # Initialiser à None

# Essayer d'initialiser la connexion série au démarrage
try:
    ser = serial.Serial(ESP_PORT, BAUD_RATE, timeout=1)
    # Ne pas bloquer trop longtemps ici, la reconnexion peut être tentée plus tard si nécessaire
    # time.sleep(2) 
    if ser.is_open:
        print(f"Connexion série initialisée sur {ESP_PORT}")
    else:
        print(f"Impossible d'ouvrir la connexion série sur {ESP_PORT} au démarrage.")
        ser = None # S'assurer que ser est None si l'ouverture échoue
except serial.SerialException as e:
    print(f"Erreur lors de l'initialisation de la connexion série: {e}")
    ser = None
except Exception as e:
    print(f"Autre erreur lors de l'initialisation: {e}")
    ser = None

@app.route('/api/test', methods=['GET'])
def test_api():
    # Cet endpoint teste si Flask fonctionne, pas la connexion ESP32
    return jsonify({'message': 'API Flask is working'})

@app.route('/api/system/info', methods=['GET'])
def get_system_info():
    # Repris de votre code original
    try:
        cpu_temperature_raw = os.popen("vcgencmd measure_temp").readline()
        cpu_temperature = cpu_temperature_raw.replace("temp=","").replace("'C\n","").strip()
        if not cpu_temperature: # Fallback si vcgencmd échoue ou n'est pas dispo
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
    # Repris de votre code original
    try:
        response = requests.get('http://localhost:8080/?action=stream', stream=True, timeout=2) # Timeout réduit
        response.raise_for_status()  
        if 'multipart/x-mixed-replace' in response.headers.get('Content-Type', ''):
            return jsonify({'status': 'OK', 'message': 'Stream is available'})
        else:
            return jsonify({'status': 'Error', 'message': 'Unexpected content type'}), 500
    except requests.exceptions.RequestException as e:
        # Log l'erreur côté serveur pour le débogage
        print(f"Erreur camera status: {e}") 
        return jsonify({'status': 'Error', 'message': f'Stream unavailable: {e}'}), 500
    except Exception as e:
        print(f"Erreur inattendue camera status: {e}")
        return jsonify({'status': 'Error', 'message': f'Unexpected error: {e}'}), 500


@app.route('/api/motors/control', methods=['POST'])
def control_motors():
    # Repris de votre code original, avec vérification de 'ser'
    if ser is None or not ser.is_open:
        # Essayer de rouvrir une fois si la connexion a été perdue
        global ser
        try:
            print("Tentative de reconnexion série pour commande moteurs...")
            if ser: ser.close()
            ser = serial.Serial(ESP_PORT, BAUD_RATE, timeout=1)
            if not ser.is_open: raise serial.SerialException("Impossible de rouvrir le port.")
            print("Reconnexion série réussie.")
        except Exception as e:
            print(f"Échec de la reconnexion série: {e}")
            ser = None
            return jsonify({"status": "error", "message": f"Connexion USB non disponible: {e}"}), 500

    try:
        data = request.json
        motor_values_to_send = []
        command_parts = []
        
        for i in range(1, 9): # Pour 8 moteurs, M1 à M8
            motor_key = f'm{i}'
            motor_value = max(1000, min(2000, int(data.get(motor_key, 1000))))
            command_parts.append(f"M{i}:{motor_value}")
        
        command_to_esp = ";".join(command_parts) + ";\n" # Format: M1:1500;M2:1500;...M8:1500;
        
        print(f"Envoi commande moteurs: {command_to_esp.strip()}")
        ser.write(command_to_esp.encode())
        
        # Attendre une réponse simple (comme dans votre code original)
        # Mettre un timeout plus court pour éviter de bloquer trop longtemps
        ser.timeout = 0.5 # Timeout de 500ms pour la lecture de l'ACK
        response = ser.readline().decode('utf-8').strip()
        ser.timeout = 1 # Remettre le timeout par défaut
        print(f"Réponse moteurs: {response}")
        
        # Vérifier si la réponse est celle attendue (adapté de votre code ESP32)
        if "MOTORS_VALUES_STORED" in response or "MOTORS_OK" in response: # Accepter les deux réponses possibles
             status = "success"
        else:
             status = "warning" # ou "error" si vous préférez

        return jsonify({
            "status": status,
            "command_sent": command_to_esp.strip(),
            "response_from_esp32": response or "No response" # Fournir une valeur par défaut
        })
            
    except serial.SerialTimeoutException:
        print("Timeout lors de l'attente de la réponse moteur.")
        return jsonify({"status": "error", "message": "Timeout: No response from ESP32 for motor command."}), 500
    except Exception as e:
        print(f"Erreur dans /api/motors/control: {e}")
        # Essayer de fermer et invalider ser en cas d'erreur grave
        global ser
        try: 
            if ser: ser.close()
        except: pass
        ser = None
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/led/control', methods=['POST'])
def control_led():
    # Repris de votre code original, avec vérification de 'ser'
    if ser is None or not ser.is_open:
        # Essayer de rouvrir une fois
        global ser
        try:
            print("Tentative de reconnexion série pour commande LED...")
            if ser: ser.close()
            ser = serial.Serial(ESP_PORT, BAUD_RATE, timeout=1)
            if not ser.is_open: raise serial.SerialException("Impossible de rouvrir le port.")
            print("Reconnexion série réussie.")
        except Exception as e:
            print(f"Échec de la reconnexion série: {e}")
            ser = None
            return jsonify({"status": "error", "message": f"Connexion USB non disponible: {e}"}), 500
    
    try:
        data = request.json
        brightness = max(0, min(100, int(data.get('brightness', 0)))) # 0-100%
        command_to_esp = f"LED:{brightness};\n"
        
        print(f"Envoi commande LED: {command_to_esp.strip()}")
        ser.write(command_to_esp.encode())
        
        # Attendre une réponse simple
        ser.timeout = 0.5 # Timeout court
        response = ser.readline().decode('utf-8').strip()
        ser.timeout = 1 # Remettre timeout par défaut
        print(f"Réponse LED: {response}")

        # Vérifier la réponse attendue ACK_LED:valeur
        ack_pattern = re.compile(r'ACK_LED:(\d+)')
        match = ack_pattern.match(response)
        
        if match and int(match.group(1)) == brightness:
            status = "success"
        else:
            status = "warning" # Ou "error"

        return jsonify({
            "status": status,
            "command_sent": command_to_esp.strip(),
            "response_from_esp32": response or "No response",
            "brightness_set": brightness
        })
            
    except serial.SerialTimeoutException:
        print("Timeout lors de l'attente de la réponse LED.")
        return jsonify({"status": "error", "message": "Timeout: No response from ESP32 for LED command."}), 500
    except Exception as e:
        print(f"Erreur dans /api/led/control: {e}")
        global ser
        try: 
            if ser: ser.close()
        except: pass
        ser = None
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/orientation', methods=['GET'])
def get_orientation():
    """ Renvoie les données d'orientation du capteur IMU (via ESP32) """
    # Repris de votre code original, avec vérification de 'ser'
    if ser is None or not ser.is_open:
        # Essayer de rouvrir une fois
        global ser
        try:
            print("Tentative de reconnexion série pour orientation...")
            if ser: ser.close()
            ser = serial.Serial(ESP_PORT, BAUD_RATE, timeout=1)
            if not ser.is_open: raise serial.SerialException("Impossible de rouvrir le port.")
            print("Reconnexion série réussie.")
        except Exception as e:
            print(f"Échec de la reconnexion série: {e}")
            ser = None
            return jsonify({"status": "error", "message": f"Connexion USB non disponible: {e}"}), 500
    
    try:
        command_to_esp = b"GET_ORIENTATION\n"
        print(f"Envoi commande orientation: {command_to_esp.strip()}")
        ser.write(command_to_esp)
        
        # Attendre la réponse
        ser.timeout = 1 # Timeout un peu plus long pour la réponse capteur
        response = ser.readline().decode('utf-8').strip()
        ser.timeout = 1 # Remettre timeout par défaut
        print(f"Réponse orientation: {response}")
        
        # Analyser la réponse avec une expression régulière (identique à votre code original)
        orientation_pattern = re.compile(r'O:(-?\d+\.?\d*),(-?\d+\.?\d*),(-?\d+\.?\d*),(\d+),(\d+),(\d+),(\d+)')
        match = orientation_pattern.match(response)
        
        if match:
            # Stocker les données (optionnel, mais peut être utile)
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
                "message": "Format de réponse d'orientation invalide de l'ESP32.",
                "response_from_esp32": response or "No response"
            }), 500
            
    except serial.SerialTimeoutException:
        print("Timeout lors de l'attente de la réponse orientation.")
        return jsonify({"status": "error", "message": "Timeout: No response from ESP32 for orientation data."}), 500
    except Exception as e:
        print(f"Erreur dans /api/orientation: {e}")
        global ser
        try: 
            if ser: ser.close()
        except: pass
        ser = None
        return jsonify({
            "status": "error",
            "message": f"Erreur lors de la lecture des données d'orientation: {e}"
        }), 500

# --- NOUVEL ENDPOINT POUR LA PROFONDEUR ---
@app.route('/api/depth', methods=['GET'])
def get_depth_data():
    """ Renvoie les données de profondeur du capteur GY-MS5837 (via ESP32) """
    if ser is None or not ser.is_open:
        # Essayer de rouvrir une fois
        global ser
        try:
            print("Tentative de reconnexion série pour profondeur...")
            if ser: ser.close()
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
        ser.write(command_to_esp)
        
        # Attendre la réponse
        ser.timeout = 1 # Timeout un peu plus long pour la réponse capteur
        response = ser.readline().decode('utf-8').strip()
        ser.timeout = 1 # Remettre timeout par défaut
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
                "message": "Format de réponse de profondeur invalide de l'ESP32.",
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
# --- FIN DU NOUVEL ENDPOINT ---

if __name__ == '__main__':
    # Lancer l'application Flask. 
    # Utiliser debug=False en production stable. debug=True est utile pour le développement.
    # host='0.0.0.0' permet d'accéder à l'API depuis d'autres machines sur le réseau.
    # threaded=True est généralement une bonne idée pour que Flask gère mieux plusieurs requêtes,
    # surtout si les opérations série prennent un peu de temps.
    print("Démarrage de l'API Flask...")
    app.run(debug=True, host='0.0.0.0', port=5000, threaded=True) 
