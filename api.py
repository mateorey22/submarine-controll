from flask import Flask, jsonify
from flask_cors import CORS
import psutil
import os
import requests
import RPi.GPIO as GPIO
from time import sleep

app = Flask(__name__)
CORS(app)

# Configuration ePWM
PWM_PIN = 23  # GPIO23, broche 16
PWM_FREQUENCY = 50  # Fréquence typique pour les ESC de brushless (en Hz), à ajuster si nécessaire
DUTY_CYCLE = 50     # 50% de la vitesse maximale (à ajuster)


GPIO.setmode(GPIO.BCM)  # Utilisation de la numérotation BCM des GPIO
GPIO.setup(PWM_PIN, GPIO.OUT)
pwm = GPIO.PWM(PWM_PIN, PWM_FREQUENCY)
pwm.start(DUTY_CYCLE)  # Démarrage du PWM avec le duty cycle initial



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
        pwm.stop()          # Arrête le PWM
        GPIO.cleanup()      # Libère les ressources GPIO