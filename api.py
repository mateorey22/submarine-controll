from flask import Flask, jsonify, request
from flask_cors import CORS
import psutil
import os
import requests
import RPi.GPIO as GPIO
import logging

# Configure logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

app = Flask(__name__)
CORS(app)

# Set the GPIO pin number
MOTOR_PIN = 18

# --- GPIO Initialization (with improved error handling) ---

def initialize_gpio():
    """Initializes GPIO and PWM, handling potential errors."""
    global pwm  #  IMPORTANT:  Declare pwm as global to modify it
    pwm = None  # Initialize to None

    try:
        # Set the GPIO mode
        GPIO.setmode(GPIO.BCM)
        logging.info("GPIO mode set to BCM")

        # Set the GPIO pin as an output
        GPIO.setup(MOTOR_PIN, GPIO.OUT)
        logging.info(f"GPIO pin {MOTOR_PIN} set as output")

        # Create a PWM instance
        pwm = GPIO.PWM(MOTOR_PIN, 50)  # Start with 50 Hz frequency
        logging.info("PWM instance created")

        # Start PWM with 0% duty cycle
        pwm.start(0)
        logging.info("PWM started with 0% duty cycle")

        logging.info("GPIO initialized successfully")
        return True  # Indicate success

    except Exception as e:
        logging.error(f"Error initializing GPIO: {e}")
        # Cleanup if initialization fails
        if pwm is not None:
            try:
                pwm.stop()
            except Exception as cleanup_e:
                logging.error(f"Error during PWM cleanup: {cleanup_e}")
        GPIO.cleanup()  # IMPORTANT: Always cleanup on error
        return False  # Indicate failure

# Initialize GPIO *before* defining routes
if not initialize_gpio():
    logging.critical("GPIO initialization failed.  Motor control will not work.")
    # Consider exiting the application here, or disabling motor-related routes
    # sys.exit(1)  #  Optionally exit


# --- Flask Routes ---

@app.route('/api/test', methods=['GET'])
def test_api():
    return jsonify({'message': 'API is working'})

@app.route('/api/system/info', methods=['GET'])
def get_system_info():
    try:
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
    except Exception as e:
        logging.error(f"Error getting system info: {e}")
        return jsonify({'status': 'Error', 'message': 'Failed to retrieve system information'}), 500

@app.route('/api/camera/status')
def camera_status():
    try:
        response = requests.get('http://localhost:8080/?action=stream', stream=True, timeout=5)
        response.raise_for_status()  # Raises HTTPError for bad requests (4XX, 5XX)
        if 'multipart/x-mixed-replace' in response.headers['Content-Type']:
            return jsonify({'status': 'OK', 'message': 'Stream is available'})
        else:
            return jsonify({'status': 'Error', 'message': 'Unexpected content type'}), 500
    except requests.exceptions.RequestException as e:
        logging.error(f"Camera status check failed: {e}")
        return jsonify({'status': 'Error', 'message': f'Stream unavailable: {e}'}), 500

@app.route('/api/motor/speed', methods=['POST'])
def set_motor_speed():
    if pwm is None:
        logging.error("PWM is not initialized")
        return jsonify({'status': 'Error', 'message': 'PWM is not initialized'}), 500

    try:
        speed = request.get_json().get('speed')
        if speed is None:
            return jsonify({'status': 'Error', 'message': 'Speed parameter is required'}), 400

        # Ensure speed is an integer and within bounds.  Convert to int!
        speed = int(speed)  # Convert to integer
        speed = max(0, min(100, speed))

        logging.info(f"Setting motor speed to {speed}%")
        pwm.ChangeDutyCycle(speed)
        logging.info(f"Motor speed set to {speed}% successfully")
        return jsonify({'status': 'OK', 'message': f'Motor speed set to {speed}%'})

    except ValueError:
        logging.error("Invalid speed value received (not an integer)")
        return jsonify({'status': 'Error', 'message': 'Invalid speed value.  Must be an integer.'}), 400
    except Exception as e:
        logging.error(f"Error setting motor speed: {e}")
        return jsonify({'status': 'Error', 'message': f'Error setting motor speed: {e}'}), 500

def cleanup_gpio():
    """Cleans up GPIO resources on application exit."""
    if pwm is not None:
        try:
            pwm.stop()
            logging.info("PWM stopped")
        except Exception as e:
            logging.error(f"Error stopping PWM: {e}")
    GPIO.cleanup()
    logging.info("GPIO cleaned up")

if __name__ == '__main__':
    try:
        app.run(debug=True, host='0.0.0.0', port=5000)
    finally:
        cleanup_gpio()  # Always cleanup GPIO on exit