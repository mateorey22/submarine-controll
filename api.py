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
ESP_PORT = '/dev/ttyUSB0'  # Port USB du Raspberry Pi connecté à l'ESP32 S3
BAUD_RATE = 115200
ser = None

# Liste des ports USB possibles pour l'ESP32 S3 (utilisée uniquement pour la reconnexion)
POSSIBLE_PORTS = [
    '/dev/ttyUSB0',  # Port USB standard sur Raspberry Pi/Linux
    '/dev/ttyACM0',  # Port ACM possible pour ESP32 S3 en mode CDC
    '/dev/ttyS0',    # Port série possible
    'COM3',          # Pour Windows (si utilisé pour tests)
    'COM4',          # Pour Windows (si utilisé pour tests)
    'COM5'           # Pour Windows (si utilisé pour tests)
]

# Tentative de connexion initiale (comme avant)
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

@app.route('/api/serial/test', methods=['GET'])
def test_serial():
    global ser
    
    # Statut actuel de la connexion
    connection_status = {
        "connected": ser is not None,
        "port": None,
        "baud_rate": BAUD_RATE,
        "available_ports": []
    }
    
    # Récupérer le port actuel si connecté
    if ser is not None:
        try:
            connection_status["port"] = ser.port
        except:
            connection_status["port"] = "Unknown"
    
    # Lister les ports série disponibles de manière sécurisée
    try:
        # Essayer d'importer le module pour lister les ports
        try:
            import serial.tools.list_ports
            ports = list(serial.tools.list_ports.comports())
            for port in ports:
                connection_status["available_ports"].append({
                    "device": port.device,
                    "description": port.description,
                    "hwid": port.hwid
                })
        except ImportError:
            # Si le module n'est pas disponible, utiliser une méthode alternative
            # Vérifier manuellement les ports communs
            for port_name in POSSIBLE_PORTS:
                try:
                    # Essayer d'ouvrir brièvement le port pour voir s'il existe
                    test_ser = serial.Serial(port_name, BAUD_RATE, timeout=0.1)
                    test_ser.close()
                    connection_status["available_ports"].append({
                        "device": port_name,
                        "description": "Port détecté",
                        "hwid": "N/A"
                    })
                except:
                    # Le port n'est pas disponible, continuer
                    pass
    except Exception as e:
        connection_status["port_list_error"] = str(e)
    
    # Si demande de reconnexion
    reconnect = request.args.get('reconnect', 'false').lower() == 'true'
    if reconnect:
        connection_status["reconnect_attempted"] = True
        
        # Fermer la connexion existante si présente
        if ser is not None:
            try:
                ser.close()
            except:
                pass
            ser = None
        
        # Tenter de se reconnecter
        for port in POSSIBLE_PORTS:
            try:
                print(f"Tentative de reconnexion sur {port}...")
                ser = serial.Serial(port, BAUD_RATE, timeout=1)
                time.sleep(1)
                
                # Tester la connexion avec gestion d'erreur
                try:
                    test_command = "M1:1000;M2:1000;M3:1000;M4:1000;M5:1000;M6:1000;M7:1000;M8:1000;\n"
                    ser.write(test_command.encode())
                    
                    # Lire la réponse avec timeout
                    response = ""
                    start_time = time.time()
                    while time.time() - start_time < 1.0:
                        if ser.in_waiting > 0:
                            try:
                                line = ser.readline().decode().strip()
                                if line:
                                    response += line + " "
                            except:
                                break
                        else:
                            time.sleep(0.01)
                except Exception as e:
                    response = f"Erreur lors du test: {e}"
                
                connection_status["reconnect_success"] = True
                connection_status["connected"] = True
                connection_status["port"] = port
                connection_status["test_response"] = response
                print(f"Reconnexion USB réussie sur {port}")
                break
            except Exception as e:
                print(f"Échec de reconnexion sur {port}: {e}")
                if ser:
                    try:
                        ser.close()
                    except:
                        pass
                    ser = None
                connection_status["reconnect_error"] = str(e)
    
    return jsonify(connection_status)

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
    global ser
    
    # Vérifier si la connexion série est disponible
    if ser is None:
        # Tentative de reconnexion simplifiée
        try:
            # Essayer d'abord le port par défaut
            print(f"Tentative de reconnexion sur {ESP_PORT}...")
            ser = serial.Serial(ESP_PORT, BAUD_RATE, timeout=1)
            time.sleep(1)
            print(f"Reconnexion USB réussie sur {ESP_PORT}")
        except Exception as e:
            print(f"Échec de reconnexion sur le port par défaut: {e}")
            # Si le port par défaut échoue, essayer les autres ports
            for port in POSSIBLE_PORTS:
                if port == ESP_PORT:
                    continue  # Déjà essayé
                try:
                    print(f"Tentative de reconnexion sur {port}...")
                    ser = serial.Serial(port, BAUD_RATE, timeout=1)
                    time.sleep(1)
                    print(f"Reconnexion USB réussie sur {port}")
                    break
                except Exception as e:
                    print(f"Échec de reconnexion sur {port}: {e}")
        
        # Si toujours pas de connexion
        if ser is None:
            return jsonify({
                "status": "error", 
                "message": "Connexion USB non disponible. Vérifiez que l'ESP32 S3 est bien connecté."
            }), 500
    
    try:
        # Vérifier si la connexion est toujours valide
        if not ser.is_open:
            try:
                ser.open()
            except Exception as e:
                print(f"Erreur lors de la réouverture du port série: {e}")
                ser = None
                return jsonify({
                    "status": "error", 
                    "message": "Port série fermé et impossible à rouvrir"
                }), 500
        
        # Récupérer et valider les données JSON
        data = request.json
        if not data:
            return jsonify({"status": "error", "message": "Données JSON manquantes"}), 400
            
        # Validation des valeurs PWM (1000-2000 typique pour ESC)
        motor_values = []
        
        # Récupération des valeurs pour les 8 moteurs
        for i in range(1, 9):
            motor_key = f'm{i}'
            # Utiliser 1000 (arrêt) comme valeur par défaut si non spécifiée
            try:
                motor_value = max(1000, min(2000, int(data.get(motor_key, 1000))))
            except (ValueError, TypeError):
                motor_value = 1000  # Valeur sécurisée en cas d'erreur
            motor_values.append(motor_value)
        
        # Format de commande : "M1:1500;M2:1500;M3:1500;...M8:1500;\n"
        command = ""
        for i, value in enumerate(motor_values, 1):
            command += f"M{i}:{value};"
        command += "\n"
        
        # Envoyer la commande avec gestion d'erreur robuste
        try:
            # Vider les buffers avant d'envoyer une nouvelle commande
            ser.reset_input_buffer()
            ser.reset_output_buffer()
            
            # Envoyer la commande
            ser.write(command.encode())
        except Exception as e:
            # En cas d'erreur d'écriture, la connexion est probablement perdue
            print(f"Erreur d'écriture sur le port série: {e}")
            if ser:
                try:
                    ser.close()
                except:
                    pass
                ser = None
            return jsonify({
                "status": "error", 
                "message": f"Erreur de communication avec l'ESP32: {e}"
            }), 500
        
        # Attendre une réponse avec timeout
        response = ""
        start_time = time.time()
        timeout_duration = 1.0  # 1 seconde maximum d'attente
        
        while time.time() - start_time < timeout_duration:
            try:
                if ser and ser.in_waiting > 0:
                    line = ser.readline().decode().strip()
                    if line.startswith("ACK:"):
                        response = line
                        break
                    elif line:
                        response += line + " "
            except Exception as e:
                response = f"Erreur de lecture: {e}"
                break
            time.sleep(0.01)  # Petit délai pour éviter de surcharger le CPU
        
        # Si aucune réponse après le timeout
        if not response:
            response = "Aucune réponse (timeout)"
        
        return jsonify({
            "status": "success", 
            "command": command,
            "response": response,
            "motor_values": motor_values
        })
    except Exception as e:
        print(f"Erreur dans control_motors: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/orientation', methods=['GET'])
def get_orientation():
    """
    Fonction temporairement désactivée - retourne des valeurs fictives
    """
    return jsonify({
        "status": "warning",
        "message": "Fonctionnalité temporairement désactivée",
        "data": {
            "roll": 0.0,
            "pitch": 0.0,
            "yaw": 0.0,
            "calibration": {
                "system": 0,
                "gyro": 0,
                "accel": 0,
                "mag": 0
            },
            "timestamp": time.time()
        }
    })

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
