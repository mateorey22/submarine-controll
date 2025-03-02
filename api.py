from flask import Flask, jsonify
from flask_cors import CORS
import psutil
import os
import subprocess

app = Flask(__name__)
CORS(app)

def is_camera_connected():
    try:
        # Run v4l2-ctl command to list devices
        result = subprocess.run(['v4l2-ctl', '--list-devices'], capture_output=True, text=True, check=True)
        # Check if any device is listed
        return "Cannot open device" not in result.stdout
    except subprocess.CalledProcessError:
        return False
    except FileNotFoundError:
        # v4l2-ctl is not installed
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
