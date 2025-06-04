from flask import Flask, jsonify, request
from flask_cors import CORS
import psutil
import os
import requests
import serial
import time
import re
import threading
import json

app = Flask(__name__)
CORS(app)

# Configuration USB pour ESP32 S3
ESP_PORT = '/dev/ttyACM1' # Port USB du Raspberry Pi connecté à l'ESP32 S3
BAUD_RATE = 115200

# Global variables for sensor data
latest_sensor_data = {
    'orientation': {'roll': 0.0, 'pitch': 0.0, 'yaw': 0.0, 'calibration': {'system': 0, 'gyro': 0, 'accel': 0, 'mag': 0}},
    'depth': 0.0,
    'temperature': 20.0,
    'timestamp': time.time()
}

# Serial connection
ser = None

def init_serial_connection():
    global ser
    try:
        ser = serial.Serial(ESP_PORT, BAUD_RATE, timeout=1)
        time.sleep(2)  # Laisse le temps à la connexion de s'établir
        print(f"Connexion USB établie sur {ESP_PORT}")
        return True
    except Exception as e:
        print(f"Erreur lors de l'initialisation de la connexion USB: {e}")
        ser = None
        return False

def send_serial_command(command):
    """Helper function to send commands to ESP32"""
    global ser
    if ser is None:
        return False
    
    try:
        ser.write(command.encode())
        return True
    except Exception as e:
        print(f"Error sending command: {e}")
        return False

# Initialize serial connection
init_serial_connection()

@app.route('/api/test', methods=['GET'])
def test_api():
    return jsonify({'message': 'Enhanced Submarine API is working'})

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

@app.route('/api/motors/control', methods=['POST'])
def control_motors():
    """Legacy motor control endpoint - maintains backward compatibility"""
    if ser is None:
        return jsonify({"status": "error", "message": "Connexion USB non disponible"}), 500
    
    try:
        data = request.json
        motor_values = []
        
        # Récupération des valeurs pour les 8 moteurs
        for i in range(1, 9):
            motor_key = f'm{i}'
            motor_value = max(1000, min(2000, int(data.get(motor_key, 1000))))
            motor_values.append(motor_value)
        
        # Format de commande : "M1:1500;M2:1500;M3:1500;...M8:1500;\n"
        command = ""
        for i, value in enumerate(motor_values, 1):
            command += f"M{i}:{value};"
        command += "\n"
        
        # Envoyer la commande
        ser.write(command.encode())
        
        # Attendre une réponse simple
        try:
            response = ser.readline().decode().strip()
        except Exception as e:
            response = f"Erreur: {e}"
        
        return jsonify({
            "status": "success", 
            "command": command,
            "response": response
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/control/high_level', methods=['POST'])
def high_level_control():
    """New high-level control endpoint for enhanced submarine control"""
    if ser is None:
        return jsonify({"status": "error", "message": "Connexion USB non disponible"}), 500
    
    try:
        data = request.json
        commands_sent = []
        
        # Process different types of high-level commands
        if 'forward_thrust' in data:
            thrust = max(-1.0, min(1.0, float(data['forward_thrust'])))
            command = f"CMD:FORWARD,VAL:{thrust}\n"
            ser.write(command.encode())
            commands_sent.append(f"Forward thrust: {thrust}")
        
        if 'strafe_thrust' in data:
            thrust = max(-1.0, min(1.0, float(data['strafe_thrust'])))
            command = f"CMD:STRAFE,VAL:{thrust}\n"
            ser.write(command.encode())
            commands_sent.append(f"Strafe thrust: {thrust}")
        
        if 'vertical_thrust' in data:
            thrust = max(-1.0, min(1.0, float(data['vertical_thrust'])))
            command = f"CMD:VERTICAL,VAL:{thrust}\n"
            ser.write(command.encode())
            commands_sent.append(f"Vertical thrust: {thrust}")
        
        if 'yaw_rate' in data:
            rate = max(-1.0, min(1.0, float(data['yaw_rate'])))
            command = f"CMD:YAW_RATE,VAL:{rate}\n"
            ser.write(command.encode())
            commands_sent.append(f"Yaw rate: {rate}")
        
        if 'target_pitch' in data:
            pitch = max(-45.0, min(45.0, float(data['target_pitch'])))
            command = f"TARGET:PITCH,VAL:{pitch}\n"
            ser.write(command.encode())
            commands_sent.append(f"Target pitch: {pitch}°")
        
        if 'target_roll' in data:
            roll = max(-45.0, min(45.0, float(data['target_roll'])))
            command = f"TARGET:ROLL,VAL:{roll}\n"
            ser.write(command.encode())
            commands_sent.append(f"Target roll: {roll}°")
        
        if 'target_yaw' in data:
            yaw = float(data['target_yaw'])
            command = f"TARGET:YAW,VAL:{yaw}\n"
            ser.write(command.encode())
            commands_sent.append(f"Target yaw: {yaw}°")
        
        # Wait for acknowledgments
        responses = []
        for _ in commands_sent:
            try:
                response = ser.readline().decode().strip()
                responses.append(response)
            except Exception as e:
                responses.append(f"Error: {e}")
        
        return jsonify({
            "status": "success",
            "commands_sent": commands_sent,
            "responses": responses
        })
        
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/led/control', methods=['POST'])
def control_led():
    if ser is None:
        return jsonify({"status": "error", "message": "Connexion USB non disponible"}), 500
    
    try:
        data = request.json
        brightness = max(0, min(100, int(data.get('brightness', 0))))
        
        command = f"LED:{brightness};\n"
        ser.write(command.encode())
        
        try:
            response = ser.readline().decode().strip()
        except Exception as e:
            response = f"Erreur: {e}"
        
        return jsonify({
            "status": "success", 
            "command": command,
            "response": response,
            "brightness": brightness
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/orientation', methods=['GET'])
def get_orientation():
    """Enhanced orientation endpoint that returns all sensor data"""
    if ser is None:
        return jsonify({"status": "error", "message": "Connexion USB non disponible"}), 500
    
    try:
        # Envoyer une commande pour demander les données d'orientation
        ser.write(b"GET_ORIENTATION\n")
        
        # Attendre la réponse
        response = ser.readline().decode().strip()
        
        # Parse the extended response format
        # Expected: "O:<roll>,<pitch>,<yaw>,<s_cal>,<g_cal>,<a_cal>,<m_cal>;D:<depth>;T:<temp>;"
        parsed_data = parse_extended_sensor_data(response)
        
        if parsed_data:
            # Update global sensor data
            global latest_sensor_data
            latest_sensor_data = parsed_data
            latest_sensor_data['timestamp'] = time.time()
            
            return jsonify({
                "status": "success",
                "data": latest_sensor_data
            })
        else:
            return jsonify({
                "status": "error",
                "message": "Format de réponse invalide",
                "response": response
            }), 500
            
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": f"Erreur lors de la lecture des données d'orientation: {e}"
        }), 500

@app.route('/api/environment', methods=['GET'])
def get_environment():
    """New endpoint specifically for depth and temperature data"""
    global latest_sensor_data
    
    return jsonify({
        "status": "success",
        "data": {
            "depth": latest_sensor_data.get('depth', 0.0),
            "temperature": latest_sensor_data.get('temperature', 20.0),
            "timestamp": latest_sensor_data.get('timestamp', time.time())
        }
    })

@app.route('/api/telemetry', methods=['GET'])
def get_telemetry():
    """Comprehensive telemetry endpoint combining all sensor data"""
    global latest_sensor_data
    
    # Get fresh orientation data
    if ser is not None:
        try:
            ser.write(b"GET_ORIENTATION\n")
            response = ser.readline().decode().strip()
            parsed_data = parse_extended_sensor_data(response)
            if parsed_data:
                latest_sensor_data = parsed_data
                latest_sensor_data['timestamp'] = time.time()
        except Exception as e:
            print(f"Error updating telemetry: {e}")
    
    return jsonify({
        "status": "success",
        "data": latest_sensor_data
    })

@app.route('/api/stabilization/toggle', methods=['POST'])
def toggle_stabilization():
    """Toggle PID stabilization on/off"""
    if ser is None:
        return jsonify({"status": "error", "message": "Connexion USB non disponible"}), 500
    
    try:
        data = request.json
        enabled = data.get('enabled', True)
        
        # Send correct stabilization toggle command to match ESP32 implementation
        command = f"STABILIZE:{1 if enabled else 0}\n"
        if send_serial_command(command):
            try:
                response = ser.readline().decode().strip()
            except Exception as e:
                response = f"Error: {e}"
            
            return jsonify({
                "status": "success",
                "stabilization_enabled": enabled,
                "command": command.strip(),
                "response": response
            })
        else:
            return jsonify({
                "status": "error",
                "message": "Failed to send stabilization command to ESP32"
            }), 500
        
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

def parse_extended_sensor_data(response):
    """Parse the extended sensor data format from ESP32"""
    try:
        # Expected format: "O:<roll>,<pitch>,<yaw>,<s_cal>,<g_cal>,<a_cal>,<m_cal>;D:<depth>;T:<temp>;"
        
        # Parse orientation data
        orientation_match = re.search(r'O:(-?\d+\.?\d*),(-?\d+\.?\d*),(-?\d+\.?\d*),(\d+),(\d+),(\d+),(\d+)', response)
        if not orientation_match:
            return None
        
        roll = float(orientation_match.group(1))
        pitch = float(orientation_match.group(2))
        yaw = float(orientation_match.group(3))
        sys_cal = int(orientation_match.group(4))
        gyro_cal = int(orientation_match.group(5))
        accel_cal = int(orientation_match.group(6))
        mag_cal = int(orientation_match.group(7))
        
        # Parse depth data
        depth_match = re.search(r'D:(-?\d+\.?\d*)', response)
        depth = float(depth_match.group(1)) if depth_match else 0.0
        
        # Parse temperature data
        temp_match = re.search(r'T:(-?\d+\.?\d*)', response)
        temperature = float(temp_match.group(1)) if temp_match else 20.0
        
        return {
            'orientation': {
                'roll': roll,
                'pitch': pitch,
                'yaw': yaw,
                'calibration': {
                    'system': sys_cal,
                    'gyro': gyro_cal,
                    'accel': accel_cal,
                    'mag': mag_cal
                }
            },
            'depth': depth,
            'temperature': temperature
        }
        
    except Exception as e:
        print(f"Error parsing sensor data: {e}")
        return None

@app.route('/api/serial/test', methods=['GET'])
def test_serial():
    """Test and optionally reconnect serial connection"""
    global ser
    
    reconnect = request.args.get('reconnect', 'false').lower() == 'true'
    
    if reconnect or ser is None:
        # Try to reconnect
        if ser is not None:
            try:
                ser.close()
            except:
                pass
        
        success = init_serial_connection()
        if not success:
            return jsonify({
                "connected": False,
                "port": ESP_PORT,
                "message": "Failed to connect to ESP32"
            })
    
    # Test the connection
    try:
        if ser is not None:
            # Send a test command
            ser.write(b"GET_ORIENTATION\n")
            response = ser.readline().decode().strip()
            
            return jsonify({
                "connected": True,
                "port": ESP_PORT,
                "test_response": response,
                "message": "ESP32 connection successful"
            })
        else:
            return jsonify({
                "connected": False,
                "port": ESP_PORT,
                "message": "Serial connection not available"
            })
            
    except Exception as e:
        return jsonify({
            "connected": False,
            "port": ESP_PORT,
            "error": str(e),
            "message": "Serial connection test failed"
        })

# New endpoint for raw IMU data
@app.route('/api/raw_imu_data', methods=['GET'])
def get_raw_imu_data():
        """Endpoint for raw IMU sensor data including calibration status"""
        if ser is None:
            return jsonify({"status": "error", "message": "Connexion USB non disponible"}), 500
        
        try:
            # Send command to request raw IMU data
            ser.write(b"GET_RAW_IMU\n")
            
            # Wait for response
            response = ser.readline().decode().strip()
            
            # Parse the response format
            # Expected: "RAW:<ax>,<ay>,<az>,<gx>,<gy>,<gz>,<mx>,<my>,<mz>;O:<roll>,<pitch>,<yaw>,<s_cal>,<g_cal>,<a_cal>,<m_cal>;"
            raw_match = re.search(r'RAW:(-?\d+\.?\d*),(-?\d+\.?\d*),(-?\d+\.?\d*),(-?\d+\.?\d*),(-?\d+\.?\d*),(-?\d+\.?\d*),(-?\d+\.?\d*),(-?\d+\.?\d*),(-?\d+\.?\d*)', response)
            orientation_match = re.search(r'O:(-?\d+\.?\d*),(-?\d+\.?\d*),(-?\d+\.?\d*),(\d+),(\d+),(\d+),(\d+)', response)
            
            if not raw_match or not orientation_match:
                return jsonify({
                    "status": "error",
                    "message": "Format de réponse invalide",
                    "response": response
                }), 500
            
            # Parse raw data
            accel_x = float(raw_match.group(1))
            accel_y = float(raw_match.group(2))
            accel_z = float(raw_match.group(3))
            gyro_x = float(raw_match.group(4))
            gyro_y = float(raw_match.group(5))
            gyro_z = float(raw_match.group(6))
            mag_x = float(raw_match.group(7))
            mag_y = float(raw_match.group(8))
            mag_z = float(raw_match.group(9))
            
            # Parse orientation data
            roll = float(orientation_match.group(1))
            pitch = float(orientation_match.group(2))
            yaw = float(orientation_match.group(3))
            sys_cal = int(orientation_match.group(4))
            gyro_cal = int(orientation_match.group(5))
            accel_cal = int(orientation_match.group(6))
            mag_cal = int(orientation_match.group(7))
            
            return jsonify({
                "status": "success",
                "data": {
                    "raw": {
                        "accel": {
                            "x": accel_x,
                            "y": accel_y,
                            "z": accel_z
                        },
                        "gyro": {
                            "x": gyro_x,
                            "y": gyro_y,
                            "z": gyro_z
                        },
                        "mag": {
                            "x": mag_x,
                            "y": mag_y,
                            "z": mag_z
                        }
                    },
                    "orientation": {
                        "roll": roll,
                        "pitch": pitch,
                        "yaw": yaw
                    },
                    "calibration": {
                        "system": sys_cal,
                        "gyro": gyro_cal,
                        "accel": accel_cal,
                        "mag": mag_cal
                    }
                }
            })
            
        except Exception as e:
            return jsonify({
                "status": "error",
                "message": f"Erreur lors de la lecture des données IMU brutes: {e}"
            }), 500

# Calibration endpoints
@app.route('/api/calibration/<command>', methods=['POST'])
def calibration_command(command):
        """Handle IMU calibration commands"""
        if ser is None:
            return jsonify({"status": "error", "message": "Connexion USB non disponible"}), 500
        
        valid_commands = ['start', 'cancel', 'complete', 'reset', 'save']
        if command not in valid_commands:
            return jsonify({"status": "error", "message": f"Commande de calibration invalide: {command}"}), 400
        
        try:
            # Send calibration command to ESP32
            ser.write(f"CALIBRATE:{command}\n".encode())
            
            # Wait for response
            response = ser.readline().decode().strip()
            
            return jsonify({
                "status": "success",
                "command": command,
                "response": response
            })
            
        except Exception as e:
            return jsonify({
                "status": "error",
                "message": f"Erreur lors de l'envoi de la commande de calibration: {e}"
            }), 500

if __name__ == '__main__':
    print("Starting Enhanced Submarine API...")
    print("New endpoints:")
    print("- /api/control/high_level - High-level movement commands")
    print("- /api/environment - Depth and temperature data")
    print("- /api/telemetry - Complete sensor telemetry")
    print("- /api/stabilization/toggle - Toggle PID stabilization")
    print("- /api/raw_imu_data - Raw IMU sensor data")
    print("- /api/calibration/<command> - IMU calibration commands")
    
    app.run(debug=True, host='0.0.0.0', port=5000)
