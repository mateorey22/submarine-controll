from flask import Flask, jsonify
from flask_cors import CORS
import psutil
import os
import requests
from gpiozero import PWMOutputDevice
from time import sleep

app = Flask(__name__)
CORS(app)

pwm_device = PWMOutputDevice(18)
pwm_device.value = 0

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

@app.route('/api/motor/on', methods=['POST'])
def turn_motor_on():
    pwm_device.value = 0.1
    return jsonify({'status': 'success', 'message': 'Motor turned on'}), 200

@app.route('/api/motor/off', methods=['POST'])
def turn_motor_off():
    pwm_device.value = 0
    return jsonify({'status': 'success', 'message': 'Motor turned off'}), 200

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
