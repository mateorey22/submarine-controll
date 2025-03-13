from flask import Flask, jsonify
from flask_cors import CORS
import psutil
import os
import requests
import RPi.GPIO as GPIO
import time

app = Flask(__name__)
CORS(app)

# Configuration du GPIO pour le PWM
GPIO.setmode(GPIO.BCM)
MOTOR_PIN = 18  # Pin GPIO pour le contrôle du moteur (PWM)
GPIO.setup(MOTOR_PIN, GPIO.OUT)

# Configuration du PWM
pwm_motor = GPIO.PWM(MOTOR_PIN, 50)  # Fréquence de 50 Hz
pwm_motor.start(0)  # Démarrage avec un cycle d'utilisation de 0 (moteur arrêté)

motor_on = False

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

@app.route('/api/motor/toggle', methods=['POST'])
def motor_toggle():
    global motor_on
    motor_on = not motor_on
    if motor_on:
        pwm_motor.ChangeDutyCycle(5)  # Vitesse minimale (environ 1000µs)
        return jsonify({'status': 'OK', 'message': 'Motor started'})
    else:
        pwm_motor.ChangeDutyCycle(0)  # Arrêt du moteur
        return jsonify({'status': 'OK', 'message': 'Motor stopped'})

if __name__ == '__main__':
    try:
        app.run(debug=True, host='0.0.0.0', port=5000)
    finally:
        GPIO.cleanup()
