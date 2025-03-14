from flask import Flask, jsonify
from flask_cors import CORS
import psutil
import os
import requests
import RPi.GPIO as GPIO
from time import sleep

app = Flask(__name__)
CORS(app)

# Configuration du contrôle du moteur brushless
MOTOR_PIN = 23  # GPIO23 (broche 16)
FREQUENCY = 50  # Fréquence PWM standard pour ESC brushless (50Hz)
MIN_DUTY = 5    # Duty cycle minimum (5%)
MAX_DUTY = 10   # Duty cycle maximum (10%)
# Note: ces valeurs MIN_DUTY et MAX_DUTY sont typiques pour les ESC
# mais peuvent nécessiter un ajustement selon votre ESC spécifique

GPIO.setmode(GPIO.BCM)
GPIO.setup(MOTOR_PIN, GPIO.OUT)

# Création de l'objet PWM
motor_pwm = GPIO.PWM(MOTOR_PIN, FREQUENCY)
motor_pwm.start(0)  # Initialise à 0% (moteur arrêté)
motor_running = False

# Fonction de conversion pour mapper 0-1 à MIN_DUTY-MAX_DUTY
def speed_to_duty_cycle(speed):
    """Convertit une vitesse de 0.0 à 1.0 en duty cycle approprié pour l'ESC."""
    if speed <= 0.0:
        return 0  # Moteur arrêté
    elif speed >= 1.0:
        return MAX_DUTY
    else:
        # Interpolation linéaire entre MIN_DUTY et MAX_DUTY
        return MIN_DUTY + speed * (MAX_DUTY - MIN_DUTY)

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
    """Démarre le moteur brushless à la vitesse minimale."""
    global motor_running
    duty_cycle = speed_to_duty_cycle(0.1)  # Vitesse minimale pour démarrer
    motor_pwm.ChangeDutyCycle(duty_cycle)
    motor_running = True
    return jsonify({'status': 'OK', 'message': f'Motor started at {duty_cycle}% duty cycle'})

@app.route('/api/motor/stop', methods=['GET'])
def stop_motor():
    """Arrête le moteur brushless."""
    global motor_running
    motor_pwm.ChangeDutyCycle(0)
    motor_running = False
    return jsonify({'status': 'OK', 'message': 'Motor stopped'})

@app.route('/api/motor/speed/<float:speed>', methods=['GET'])
def set_speed(speed):
    """Ajuste la vitesse du moteur brushless (0.0 à 1.0)."""
    global motor_running
    if 0.0 <= speed <= 1.0:
        duty_cycle = speed_to_duty_cycle(speed)
        motor_pwm.ChangeDutyCycle(duty_cycle)
        motor_running = (speed > 0)
        return jsonify({'status': 'OK', 'message': f'Motor speed set to {speed*100:.1f}% (duty cycle: {duty_cycle:.1f}%)'})
    else:
        return jsonify({'status': 'Error', 'message': 'Speed must be between 0.0 and 1.0'}), 400

@app.route('/api/motor/arm', methods=['GET'])
def arm_esc():
    """Sequence d'armement pour l'ESC du moteur brushless."""
    # Séquence typique d'armement ESC
    motor_pwm.ChangeDutyCycle(0)
    sleep(1)
    motor_pwm.ChangeDutyCycle(MAX_DUTY)
    sleep(2)
    motor_pwm.ChangeDutyCycle(0)
    sleep(2)
    return jsonify({'status': 'OK', 'message': 'ESC armed successfully'})

if __name__ == '__main__':
    try:
        # Assurez-vous que le moteur est arrêté au démarrage
        motor_pwm.ChangeDutyCycle(0)
        app.run(debug=True, host='0.0.0.0', port=5000)
    finally:
        motor_pwm.stop()
        GPIO.cleanup()