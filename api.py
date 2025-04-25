from flask import Flask, jsonify, request
from flask_cors import CORS
import psutil
import os
import requests
import serial
import time
import re # Importation du module re pour les expressions régulières

app = Flask(__name__)
CORS(app)

# --- Configuration USB pour ESP32 S3 ---
# !!! IMPORTANT !!!
# Vérifie le port série correct sur ton Raspberry Pi après avoir connecté l'ESP32-S3.
# Ouvre un terminal et tape: ls /dev/tty*
# Le port sera probablement /dev/ttyACM0 pour l'USB natif de l'ESP32-S3.
# Adapte la ligne ESP_PORT ci-dessous si nécessaire.

# ESP_PORT = '/dev/ttyUSB0'  # Ancien port (souvent pour ESP8266 ou convertisseurs CH340)
ESP_PORT = '/dev/ttyACM0'  # Port probable pour ESP32-S3 (à vérifier !)

BAUD_RATE = 115200
ser = None # Initialiser ser à None

try:
    print(f"Tentative de connexion sur le port série: {ESP_PORT} à {BAUD_RATE} baud")
    # Ajout de write_timeout pour éviter des blocages potentiels à l'écriture
    ser = serial.Serial(ESP_PORT, BAUD_RATE, timeout=1, write_timeout=1)
    time.sleep(2)  # Laisse le temps à la connexion de s'établir
    # Essayer d'écrire une commande vide juste pour tester la connexion
    ser.write(b'\n')
    ser.flush()
    print(f"Connexion USB établie avec succès sur {ESP_PORT}")
except serial.SerialException as e:
    print(f"ERREUR lors de l'initialisation de la connexion USB sur {ESP_PORT}: {e}")
    print("Causes possibles :")
    print("- L'ESP32 n'est pas connecté ou n'est pas sous tension.")
    print(f"- Le port série '{ESP_PORT}' est incorrect. Vérifiez avec 'ls /dev/tty*'.")
    print("- L'utilisateur n'a pas les permissions (ajoutez-le au groupe 'dialout': sudo usermod -a -G dialout $USER et redémarrez).")
    print("- Un autre programme utilise déjà le port série (vérifiez avec 'sudo lsof | grep {ESP_PORT}').")
    # L'application peut continuer à fonctionner, mais les endpoints nécessitant 'ser' renverront une erreur.
except Exception as e:
    print(f"ERREUR inattendue lors de l'initialisation de la connexion USB: {e}")
    # Gérer d'autres exceptions potentielles

@app.route('/api/test', methods=['GET'])
def test_api():
    # Tester aussi la connexion série si possible
    if ser and ser.is_open:
        return jsonify({'message': f'API is working, Serial connection to {ESP_PORT} seems OK.'})
    else:
        return jsonify({'message': 'API is working, BUT Serial connection FAILED.'}), 500


@app.route('/api/system/info', methods=['GET'])
def get_system_info():
    cpu_temperature = "N/A"
    ram_usage = "N/A"
    load_system = "N/A"
    disk_space = "N/A"
    try:
        # Utiliser 'with open' est plus sûr pour lire les fichiers système
        with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
            temp_milli_c = int(f.read().strip())
            cpu_temperature = f"{temp_milli_c / 1000.0:.1f}'C" # Format plus propre
    except FileNotFoundError:
         print("Impossible de lire la température CPU via /sys/class/thermal/thermal_zone0/temp")
         # Essayer avec vcgencmd comme fallback (peut ne pas fonctionner sur tous les RPi ou OS)
         try:
            cpu_temperature_output = os.popen("vcgencmd measure_temp").readline()
            # Extrait uniquement la partie numérique et décimale
            match = re.search(r"temp=(\d+\.?\d*)", cpu_temperature_output)
            if match:
                cpu_temperature = f"{match.group(1)}'C"
            else:
                cpu_temperature = "N/A (vcgencmd failed)"
         except Exception as e:
             print(f"Erreur lors de l'exécution de vcgencmd: {e}")
             cpu_temperature = "N/A (vcgencmd error)"
    except Exception as e:
        print(f"Erreur lors de la lecture de la température CPU : {e}")
        cpu_temperature = "N/A (error)"

    try:
        ram_usage = psutil.virtual_memory().percent
        load_system_tuple = psutil.getloadavg() # Renvoie un tuple (1min, 5min, 15min)
        load_system = f"{load_system_tuple[0]:.2f} (1min), {load_system_tuple[1]:.2f} (5min), {load_system_tuple[2]:.2f} (15min)" # Plus informatif
        disk_space = psutil.disk_usage('/').percent
    except Exception as e:
         print(f"Erreur lors de la récupération des infos système avec psutil: {e}")

    return jsonify({
        'cpu_temperature': cpu_temperature,
        'ram_usage': ram_usage,
        'load_system': load_system,
        'disk_space': disk_space
    })

@app.route('/api/camera/status')
def camera_status():
    # URL locale du flux MJPG-Streamer
    stream_url = 'http://localhost:8080/?action=stream'
    try:
        # Utiliser un timeout raisonnable
        response = requests.get(stream_url, stream=True, timeout=2) # Timeout plus court
        response.raise_for_status()  # Lève une exception si le code HTTP n'est pas 200 OK

        # Vérifier que le content type est bien celui attendu.
        content_type = response.headers.get('Content-Type', '')
        if 'multipart/x-mixed-replace' in content_type:
            # Fermer la réponse pour libérer la connexion
            response.close()
            return jsonify({'status': 'OK', 'message': 'Stream is available'})
        else:
            response.close()
            print(f"Statut Caméra: Content-Type inattendu: {content_type}")
            return jsonify({'status': 'Error', 'message': f'Unexpected content type: {content_type}'}), 500

    except requests.exceptions.Timeout:
        print("Statut Caméra: Timeout en essayant de joindre le flux.")
        return jsonify({'status': 'Error', 'message': 'Stream unavailable: Timeout'}), 500
    except requests.exceptions.ConnectionError:
        print("Statut Caméra: Erreur de connexion au flux (mjpg-streamer est-il lancé?).")
        return jsonify({'status': 'Error', 'message': 'Stream unavailable: Connection Error'}), 500
    except requests.exceptions.RequestException as e:
        print(f"Statut Caméra: Erreur lors de la requête: {e}")
        return jsonify({'status': 'Error', 'message': f'Stream unavailable: {e}'}), 500

@app.route('/api/motors/control', methods=['POST'])
def control_motors():
    # Vérifier si la connexion série est établie
    if ser is None or not ser.is_open:
        print("ERREUR: Tentative de contrôle moteur mais la connexion USB n'est pas disponible.")
        return jsonify({"status": "error", "message": "Connexion USB non disponible"}), 500

    try:
        data = request.json
        if not data:
             return jsonify({"status": "error", "message": "Aucune donnée JSON reçue"}), 400

        # Validation des valeurs PWM (1000-2000 typique pour ESC)
        motor_values = []

        # Récupération des valeurs pour les 8 moteurs
        for i in range(1, 9): # Boucle de 1 à 8
            motor_key = f'm{i}'
            # Utiliser 1000 (arrêt) comme valeur par défaut si la clé manque
            raw_value = data.get(motor_key, 1000)
            try:
                # S'assurer que la valeur est un entier avant de la limiter
                motor_value = max(1000, min(2000, int(raw_value)))
            except (ValueError, TypeError):
                 print(f"AVERTISSEMENT: Valeur invalide reçue pour {motor_key}: {raw_value}. Utilisation de 1000.")
                 motor_value = 1000 # Mettre à 1000 si la valeur n'est pas un entier valide
            motor_values.append(motor_value)

        # Format de commande : "M1:1500;M2:1500;...;M8:1500;\n"
        command = ""
        for i, value in enumerate(motor_values, 1):
            command += f"M{i}:{value};"
        command += "\n" # Ne pas oublier le retour à la ligne final

        print(f"Envoi commande moteurs: {command.strip()}") # Afficher la commande envoyée

        # Envoyer la commande
        ser.write(command.encode('utf-8')) # Utiliser utf-8 explicitement
        ser.flush() # S'assurer que les données sont envoyées immédiatement

        # Attendre une réponse simple (ACK:...)
        response = ""
        try:
            # Lire la ligne de réponse de l'ESP32
            response_bytes = ser.readline()
            response = response_bytes.decode('utf-8').strip()
            print(f"Réponse ESP32 (Moteurs): {response}")
            # Vérifier si la réponse est bien un ACK (commence par ACK:)
            if not response.startswith("ACK:"):
                 print(f"AVERTISSEMENT: Réponse inattendue de l'ESP32 reçue: {response}")
                 # On peut quand même retourner un succès car la commande a été envoyée
        except serial.SerialTimeoutException:
             print("AVERTISSEMENT: Timeout en attendant la réponse ACK de l'ESP32.")
             response = "Timeout waiting for ACK" # Message plus clair
        except Exception as e:
            print(f"ERREUR lors de la lecture de la réponse ACK de l'ESP32: {e}")
            response = f"Error reading response: {e}"

        return jsonify({
            "status": "success",
            "sent_command": command.strip(), # Retourner la commande envoyée (sans \n)
            "received_response": response # Retourner la réponse reçue
        })
    except Exception as e:
        print(f"ERREUR dans l'endpoint /api/motors/control: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

# Endpoint pour l'orientation (retourne une erreur car l'IMU est désactivé dans ce code Arduino)
@app.route('/api/orientation', methods=['GET'])
def get_orientation():
    print("AVERTISSEMENT: Tentative de lecture de l'orientation, mais l'IMU est désactivé dans le code Arduino actuel.")
    return jsonify({
        "status": "error",
        "message": "Fonctionnalité d'orientation désactivée dans le code ESP32 actuel."
    }), 404 # Not Found or 501 Not Implemented

if __name__ == '__main__':
    # Utiliser l'hôte 0.0.0.0 pour être accessible depuis d'autres machines sur le réseau
    # debug=True est utile pour le développement, mais à désactiver en production
    print(f"Démarrage du serveur Flask sur http://0.0.0.0:5000")
    print(f"Utilisation du port série: {ESP_PORT}")
    if ser is None or not ser.is_open:
         print("ATTENTION: La connexion série n'a pas pu être établie au démarrage.")
    app.run(debug=True, host='0.0.0.0', port=5000)
