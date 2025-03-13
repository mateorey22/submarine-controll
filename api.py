from flask import Flask, jsonify, request
from flask_cors import CORS
import psutil
import os
import requests
import RPi.GPIO as GPIO  # Import the RPi.GPIO library
import logging

# Configure logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

app = Flask(__name__)
CORS(app)

# Set the GPIO pin number
MOTOR_PIN = 18

pwm = None  # Initialize pwm to None

try:
    # Set the GPIO mode
    GPIO.setmode(GPIO.BCM)
    logging.info("GPIO mode set to BCM")

    # Set the GPIO pin as an output
    GPIO.setup(MOTOR_PIN, GPIO.OUT)
    logging.info(f"GPIO pin {MOTOR_PIN} set as output")

    # Create a PWM instance
    pwm = GPIO.PWM(MOTOR_PIN, 100)  # 100 Hz frequency
    logging.info("PWM instance created")

    # Start PWM with 0% duty cycle
    pwm.start(0)
    logging.info("PWM started with 0% duty cycle")

    logging.info("GPIO initialized successfully")

except Exception as e:
    logging.error(f"Error initializing GPIO: {e}")
    # Handle the error appropriately, e.g., by disabling the motor control functionality
    pwm = None  # Set pwm to None to indicate that it's not available

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

@app.route('/api/motor/speed', methods=['POST'])
def set_motor_speed():
    speed = request.get_json().get('speed')
    if speed is None:
        return jsonify({'status': 'Error', 'message': 'Speed parameter is required'}), 400

    # Limit the speed to be between 0 and 100
    speed = max(0, min(100, speed))

    if pwm is None:
        logging.error("PWM is not initialized")
        return jsonify({'status': 'Error', 'message': 'PWM is not initialized'}), 500

    try:
        # Set the duty cycle
        pwm.ChangeDutyCycle(speed)
        return jsonify({'status': 'OK', 'message': f'Motor speed set to {speed}%'})
    except Exception as e:
        logging.error(f"Error setting motor speed: {e}")
        return jsonify({'status': 'Error', 'message': f'Error setting motor speed: {e}'}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
