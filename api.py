from flask import Flask, jsonify
from flask_cors import CORS
import psutil
import os
import requests
import RPi.GPIO as GPIO
import time
import os

app = Flask(__name__)
CORS(app)

# Configuration du GPIO pour le PWM
ESC_PIN = 18  # Broche GPIO 18 (vous pouvez changer cela)

# Détection de Raspberry Pi
if os.uname()[4].startswith("arm"):
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(ESC_PIN, GPIO.OUT)
    pwm = GPIO.PWM(ESC_PIN, 50)  # Fréquence de 50 Hz (standard pour les ESC)

    # Démarrage du PWM à mi-vitesse
    pwm.start(7.5)  # Cycle de service de 7.5% pour mi-vitesse (peut nécessiter un ajustement)
else:
    # Mock PWM object
    class MockPWM:
        def start(self, duty_cycle):
            print(f"Mock PWM start with duty cycle: {duty_cycle}")
        def stop(self):
            print("Mock PWM stop")

    pwm = MockPWM()

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

if __name__ == '__main__':
    try:
        app.run(debug=True, host='0.0.0.0', port=5000)
    finally:
        pwm.stop()
        if os.uname()[4].startswith("arm"):
            GPIO.cleanup() #nettoyage des GPIO.
