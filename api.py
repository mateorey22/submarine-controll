from flask import Flask, jsonify
from flask_cors import CORS
import psutil
import os
import requests
import RPi.GPIO as GPIO
from time import sleep, time  # Import 'time' for precise timing

app = Flask(__name__)
CORS(app)

# Configuration du contrôle du moteur
MOTOR_PIN = 23  # GPIO23 (broche 16)
FREQUENCY = 50  # Fréquence cible (Hz) - Ajustez si nécessaire
DUTY_CYCLE = 0.5  # Rapport cyclique cible (0.0 à 1.0) - 0.5 = 50%

GPIO.setmode(GPIO.BCM)
GPIO.setup(MOTOR_PIN, GPIO.OUT)

def set_motor_speed(duty_cycle):
    """Contrôle la vitesse du moteur en simulant un signal PWM."""
    period = 1.0 / FREQUENCY
    on_time = period * duty_cycle
    off_time = period - on_time

    # On utilise time() au lieu de sleep() pour la précision *dans la boucle*.
    # sleep() est suffisant pour les longues pauses, mais pas pour un PWM précis.
    while True: # Boucle infinie pour maintenir le moteur en marche
        GPIO.output(MOTOR_PIN, GPIO.HIGH)
        start_time = time()
        while time() - start_time < on_time:
            pass # Attente active (busy-wait) - consomme du CPU

        GPIO.output(MOTOR_PIN, GPIO.LOW)
        start_time = time()
        while time() - start_time < off_time:
            pass # Attente active



@app.route('/api/test', methods=['GET'])
def test_api():
    return jsonify({'message': 'API is working'})

@app.route('/api/system/info', methods=['GET'])
def get_system_info():
    cpu_temperature = os.popen("vcgencmd measure_temp").readline().replace("temp=","").replace("'C\n","")
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
        response.raise_for_status()
        if 'multipart/x-mixed-replace' in response.headers['Content-Type']:
            return jsonify({'status': 'OK', 'message': 'Stream is available'})
        else:
            return jsonify({'status': 'Error', 'message': 'Unexpected content type'}), 500

    except requests.exceptions.RequestException as e:
        return jsonify({'status': 'Error', 'message': f'Stream unavailable: {e}'}), 500


@app.route('/api/motor/start', methods=['GET'])
def start_motor():
    """Démarre le moteur (ou ajuste la vitesse si déjà démarré)."""
    global motor_thread  # Déclare motor_thread comme variable globale
    if 'motor_thread' not in globals() or not motor_thread.is_alive():
         import threading
         motor_thread = threading.Thread(target=set_motor_speed, args=(DUTY_CYCLE,))
         motor_thread.daemon = True  # Le thread s'arrêtera avec l'application principale
         motor_thread.start()
    #else:  Pas besoin de else ici car le thread tourne en boucle infinie
    return jsonify({'status': 'OK', 'message': 'Motor started'})
    

@app.route('/api/motor/stop', methods=['GET'])
def stop_motor():
    """Arrête le moteur."""
    global motor_thread
    if 'motor_thread' in globals() and motor_thread.is_alive():
        motor_thread.join(timeout=0) #On n'attend pas, timeout a 0.

    # Met la broche à LOW *après* avoir arrêté le thread
    GPIO.output(MOTOR_PIN, GPIO.LOW)
    return jsonify({'status': 'OK', 'message': 'Motor stopped'})

@app.route('/api/motor/speed/<float:speed>', methods=['GET'])
def set_speed(speed):
    """Ajuste la vitesse du moteur (rapport cyclique)."""
    global DUTY_CYCLE
    if 0.0 <= speed <= 1.0:
        DUTY_CYCLE = speed
        #On redémarre le thread pour prendre en compte le nouveau duty_cycle.
        stop_motor()
        start_motor()
        return jsonify({'status': 'OK', 'message': f'Motor speed set to {speed * 100:.2f}%'})
    else:
        return jsonify({'status': 'Error', 'message': 'Speed must be between 0.0 and 1.0'}), 400

if __name__ == '__main__':
    try:
        app.run(debug=True, host='0.0.0.0', port=5000)
    finally:
        GPIO.cleanup()