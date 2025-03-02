from flask import Flask, jsonify
from flask_cors import CORS
import psutil
import os
import subprocess

app = Flask(__name__)
CORS(app)

def is_camera_connected():
    try:
        # Check for video devices in /dev/
        video_devices = [f for f in os.listdir('/dev/') if f.startswith('video')]
        return len(video_devices) > 0
    except FileNotFoundError:
        return False

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

@app.route('/api/camera/status', methods=['GET'])
def get_camera_status():
    status = is_camera_connected()
    return jsonify({'connected': status})

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')
