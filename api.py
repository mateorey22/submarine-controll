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

# Variables pour stocker les données des capteurs
sensor_data = {
    "accelerometer": {"x": 0.0, "y": 0.0, "z": 0.0},
    "gyroscope": {"x": 0.0, "y": 0.0, "z": 0.0},
    "magnetometer": {"x": 0.0, "y": 0.0, "z": 0.0},
    "timestamp": time.time()
}

# Variables pour le lissage des données
accel_buffer = []
gyro_buffer = []
mag_buffer = []
BUFFER_SIZE = 5  # Taille du buffer pour le lissage

# Fonction pour lisser les données des capteurs (moyenne pondérée)
def smooth_sensor_data(data_buffer):
    if not data_buffer:
        return {"x": 0.0, "y": 0.0, "z": 0.0}
    
    if len(data_buffer) == 1:
        return data_buffer[0]
    
    # Calculer la moyenne pondérée des données
    # Les données plus récentes ont plus de poids
    x, y, z = 0, 0, 0
    total_weight = 0
    
    for i, data in enumerate(data_buffer):
        # Poids croissant pour les données plus récentes
        weight = i + 1
        total_weight += weight
        
        x += data["x"] * weight
        y += data["y"] * weight
        z += data["z"] * weight
    
    # Normaliser par le poids total
    return {
        "x": x / total_weight,
        "y": y / total_weight,
        "z": z / total_weight
    }

# Fonction pour lire les données série en arrière-plan
def read_serial_data():
    global sensor_data, ser, accel_buffer, gyro_buffer, mag_buffer
    
    if ser is None:
        return
    
    # Compteur pour les tentatives de reconnexion
    reconnect_attempts = 0
    max_reconnect_attempts = 5
    reconnect_delay = 2  # secondes
        
    while True:
        try:
            if ser is None or not ser.is_open:
                # Tentative de reconnexion
                if reconnect_attempts < max_reconnect_attempts:
                    print(f"Tentative de reconnexion USB ({reconnect_attempts+1}/{max_reconnect_attempts})...")
                    try:
                        ser = serial.Serial(ESP_PORT, BAUD_RATE, timeout=1)
                        time.sleep(2)  # Laisse le temps à la connexion de s'établir
                        print(f"Reconnexion USB réussie sur {ESP_PORT}")
                        reconnect_attempts = 0  # Réinitialiser le compteur en cas de succès
                    except Exception as e:
                        print(f"Échec de la reconnexion: {e}")
                        reconnect_attempts += 1
                        time.sleep(reconnect_delay)
                        continue
                else:
                    print("Nombre maximum de tentatives de reconnexion atteint. Attente avant nouvel essai.")
                    time.sleep(10)  # Attendre plus longtemps avant de réessayer
                    reconnect_attempts = 0  # Réinitialiser pour réessayer
                    continue
            
            if ser.in_waiting > 0:
                try:
                    line = ser.readline().decode('utf-8').strip()
                    
                    # Traiter les données des capteurs (format: "S:ax,ay,az,gx,gy,gz,mx,my,mz;")
                    sensor_match = re.match(r'S:([-\d\.]+),([-\d\.]+),([-\d\.]+),([-\d\.]+),([-\d\.]+),([-\d\.]+),([-\d\.]+),([-\d\.]+),([-\d\.]+);', line)
                    if sensor_match:
                        ax, ay, az, gx, gy, gz, mx, my, mz = map(float, sensor_match.groups())
                        
                        # Ajouter les nouvelles données aux buffers
                        new_accel = {"x": ax, "y": ay, "z": az}
                        new_gyro = {"x": gx, "y": gy, "z": gz}
                        new_mag = {"x": mx, "y": my, "z": mz}
                        
                        accel_buffer.append(new_accel)
                        gyro_buffer.append(new_gyro)
                        mag_buffer.append(new_mag)
                        
                        # Limiter la taille des buffers
                        if len(accel_buffer) > BUFFER_SIZE:
                            accel_buffer.pop(0)
                        if len(gyro_buffer) > BUFFER_SIZE:
                            gyro_buffer.pop(0)
                        if len(mag_buffer) > BUFFER_SIZE:
                            mag_buffer.pop(0)
                        
                        # Calculer les données lissées
                        smoothed_accel = smooth_sensor_data(accel_buffer)
                        smoothed_gyro = smooth_sensor_data(gyro_buffer)
                        smoothed_mag = smooth_sensor_data(mag_buffer)
                        
                        # Mettre à jour les données des capteurs
                        sensor_data = {
                            "accelerometer": smoothed_accel,
                            "gyroscope": smoothed_gyro,
                            "magnetometer": smoothed_mag,
                            "timestamp": time.time(),
                            "raw_data": {
                                "accelerometer": new_accel,
                                "gyroscope": new_gyro,
                                "magnetometer": new_mag
                            }
                        }
                except UnicodeDecodeError:
                    # Ignorer les erreurs de décodage (données corrompues)
                    pass
            else:
                # Petite pause pour éviter de surcharger le CPU quand il n'y a pas de données
                time.sleep(0.001)
                
        except serial.SerialException as e:
            print(f"Erreur de connexion série: {e}")
            # Marquer la connexion comme fermée pour tenter une reconnexion
            if ser:
                try:
                    ser.close()
                except:
                    pass
                ser = None
            time.sleep(reconnect_delay)
            
        except Exception as e:
            print(f"Erreur lors de la lecture des données série: {e}")
            time.sleep(1)

# Démarrer le thread de lecture série
serial_thread = threading.Thread(target=read_serial_data, daemon=True)
serial_thread.start()

@app.route('/api/test', methods=['GET'])
def test_api():
    return jsonify({'message': 'API is working'})

@app.route('/api/orientation', methods=['GET'])
def get_orientation():
    global sensor_data
    return jsonify(sensor_data)

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

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
