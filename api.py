from flask import Flask, jsonify, request
from flask_cors import CORS
import psutil
import os
import requests
from gpiozero import PWMOutputDevice
from time import sleep

app = Flask(__name__)
CORS(app)

# Configuration du moteur avec gpiozero
try:
    motor = PWMOutputDevice(18, frequency=100, initial_value=0)
except Exception as e:
    print(f"Erreur d'initialisation du moteur: {e}")
    motor = None

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
        response.raise_for_status()
        if 'multipart/x-mixed-replace' in response.headers['Content-Type']:
            return jsonify({'status': 'OK', 'message': 'Stream is available'})
        else:
            return jsonify({'status': 'Error', 'message': 'Unexpected content type'}), 500

    except requests.exceptions.RequestException as e:
        return jsonify({'status': 'Error', 'message': f'Stream unavailable: {e}'}), 500

@app.route('/api/motor/on', methods=['POST'])
def turn_motor_on():
    try:
        if motor is None:
            return jsonify({'status': 'error', 'message': 'Motor not initialized'}), 500
        motor.value = 0.1  # 10% de puissance
        return jsonify({'status': 'success', 'message': 'Motor turned on'}), 200
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/motor/off', methods=['POST'])
def turn_motor_off():
    try:
        if motor is None:
            return jsonify({'status': 'error', 'message': 'Motor not initialized'}), 500
        motor.value = 0
        return jsonify({'status': 'success', 'message': 'Motor turned off'}), 200
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/motor/speed', methods=['POST'])
def set_motor_speed():
    try:
        if motor is None:
            return jsonify({'status': 'error', 'message': 'Motor not initialized'}), 500
        speed = request.json.get('speed', 0)
        if 0 <= speed <= 100:
            motor.value = speed / 100.0  # Conversion en valeur entre 0 et 1
            return jsonify({'status': 'success', 'message': f'Motor speed set to {speed}%'}), 200
        else:
            return jsonify({'status': 'error', 'message': 'Speed must be between 0 and 100'}), 400
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

if __name__ == '__main__':
    try:
        app.run(debug=True, host='0.0.0.0', port=5000)
    finally:
        if motor is not None:
            motor.close()  # Nettoyage propre du moteur
