from flask import Flask, jsonify, request
from flask_cors import CORS
import psutil
import os
import requests
import serial
import time
import re
import threading

app = Flask(__name__)
CORS(app)

# Configuration USB pour ESP32 S3
ESP_PORT = '/dev/ttyACM1' # Port USB du Raspberry Pi connecté à l'ESP32 S3
BAUD_RATE = 115200
ser = None
serial_lock = threading.Lock() # Utiliser un verrou pour éviter les accès concurrents au port série

try:
    ser = serial.Serial(ESP_PORT, BAUD_RATE, timeout=1)
    time.sleep(2)  # Laisse le temps à la connexion de s'établir
    print(f"Connexion USB établie sur {ESP_PORT}")
    # Vider le buffer d'entrée au démarrage pour éviter de lire d'anciens messages
    if ser.isOpen():
        ser.flushInput()
        print("Buffer série vidé.")
except Exception as e:
    print(f"Erreur lors de l'initialisation de la connexion USB: {e}")
    ser = None

# Fonction pour lire une ligne du port série de manière sécurisée
def read_serial_line(timeout=1):
    if ser is None or not ser.isOpen():
        return None
    with serial_lock:
        try:
            # Utiliser le timeout configuré lors de l'ouverture du port
            line = ser.readline().decode().strip()
            return line
        except Exception as e:
            print(f"Erreur lors de la lecture série: {e}")
            return None

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

@app.route('/api/serial/test', methods=['GET'])
def test_serial_connection():
    """
    Teste la connexion série et renvoie son statut.
    Peut forcer une reconnexion si le paramètre 'reconnect=true' est présent.
    """
    reconnect_param = request.args.get('reconnect', 'false').lower() == 'true'
    
    if ser is None or not ser.isOpen() or reconnect_param:
        print("Tentative de reconnexion série...")
        try:
            global ser
            if ser and ser.isOpen():
                ser.close()
            ser = serial.Serial(ESP_PORT, BAUD_RATE, timeout=1)
            time.sleep(2) # Attendre que l'ESP32 soit prêt
            ser.flushInput() # Vider le buffer
            print(f"Reconnexion USB réussie sur {ESP_PORT}")
        except Exception as e:
            print(f"Échec de la reconnexion USB: {e}")
            ser = None

    if ser and ser.isOpen():
        # Optionnel: Envoyer une commande simple pour tester la réponse
        # ser.write(b"TEST\n") # Assurez-vous que l'ESP32 gère une commande TEST
        # test_response = read_serial_line(timeout=0.5) # Lire une réponse si attendue
        return jsonify({
            "connected": True,
            "port": ESP_PORT,
            "baudrate": BAUD_RATE,
            # "test_response": test_response # Inclure la réponse du test si applicable
        })
    else:
        # Tenter de lister les ports disponibles si la connexion échoue
        available_ports = []
        try:
            import serial.tools.list_ports
            ports = serial.tools.list_ports.comports()
            for port in ports:
                available_ports.append({"device": port.device, "description": port.description})
        except Exception as e:
            print(f"Erreur lors de la liste des ports série: {e}")

        return jsonify({
            "connected": False,
            "port": ESP_PORT,
            "message": "Impossible d'ouvrir la connexion série.",
            "available_ports": available_ports
        }), 500 # Utiliser 500 car c'est une erreur côté serveur (API)

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
            response = read_serial_line() # Utiliser la fonction sécurisée
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
            response = read_serial_line() # Utiliser la fonction sécurisée
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

        # Lire les lignes jusqu'à trouver celle qui correspond au format d'orientation
        # ou jusqu'à un timeout
        response = None
        start_time = time.time()
        timeout_seconds = 2 # Temps maximum pour attendre la réponse
        orientation_pattern = re.compile(r'O:(-?\d+\.?\d*),(-?\d+\.?\d*),(-?\d+\.?\d*),(\d+),(\d+),(\d+),(\d+)')

        while time.time() - start_time < timeout_seconds:
            line = read_serial_line()
            if line:
                match = orientation_pattern.match(line)
                if match:
                    response = line # Stocker la ligne complète qui a matché
                    break # Sortir de la boucle dès qu'on trouve la ligne d'orientation

        # Analyser la réponse avec une expression régulière
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
            # Si aucune ligne correspondante n'a été trouvée dans le délai imparti
            return jsonify({
                "status": "error",
                "message": "Format de réponse invalide",
                "response": response
            }), 500
            
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": f"Erreur lors de la lecture des données d'orientation: {e}"
        }), 500 # Utiliser 500 car c'est une erreur côté serveur (API)


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
