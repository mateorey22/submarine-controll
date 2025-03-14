import os
import time
from flask import Flask, jsonify
from flask_cors import CORS
import psutil
import requests

app = Flask(__name__)
CORS(app)

ESC = 18  # Connect the ESC in this GPIO pin
PWM_FREQUENCY = 50  # Hz

# Initialize pigpio
IS_RPI = False
pi = None
try:
    import pigpio  # Importing GPIO library
    pi = pigpio.pi()
    if not pi.connected:
        print("Can't connect to pigpio daemon. Is it running?")
        pi = None
    else:
        try:
            pi.set_mode(ESC, pigpio.OUTPUT)
            pi.set_PWM_frequency(ESC, PWM_FREQUENCY)
            pi.set_servo_pulsewidth(ESC, 0)
            IS_RPI = True
        except Exception as e:
            print(f"Error configuring PWM: {e}")
            pi = None
            IS_RPI = False
except ImportError:
    print("pigpio library not found. Please install it.")
except Exception as e:
    print(f"Error initializing pigpio: {e}")

if not IS_RPI:
    print("ESC control functions are disabled.")

max_value = 2000  # change this if your ESC's max value is different or leave it be
min_value = 700  # change this if your ESC's min value is different or leave it be

print("For first time launch, select calibrate")
print("Type the exact word for the function you want")
print("calibrate OR manual OR control OR arm OR stop")


def manual_drive():  # You will use this function to program your ESC if required
    if not IS_RPI:
        print("Manual drive not possible: pigpio not initialized.")
        return
    print("You have selected manual option so give a value between 0 and you max value")
    while True:
        inp = input()
        if inp == "stop":
            stop()
            break
        elif inp == "control":
            control()
            break
        elif inp == "arm":
            arm()
            break
        else:
            try:
                pi.set_servo_pulsewidth(ESC, int(inp))
            except ValueError:
                print("Invalid input. Please enter a number or 'stop'.")


def calibrate():  # This is the auto calibration procedure of a normal ESC
    if not IS_RPI:
        print("Calibration not possible: pigpio not initialized.")
        return
    try:
        pi.set_servo_pulsewidth(ESC, 0)
        print("Disconnect the battery and press Enter")
        inp = input()
        if inp == '':
            pi.set_servo_pulsewidth(ESC, max_value)
            print("Connect the battery NOW.. you will here two beeps, then wait for a gradual falling tone then press Enter")
            inp = input()
            if inp == '':
                pi.set_servo_pulsewidth(ESC, min_value)
                print("Wierd eh! Special tone")
                time.sleep(7)
                print("Wait for it ....")
                time.sleep(5)
                print("Im working on it, DONT WORRY JUST WAIT.....")
                pi.set_servo_pulsewidth(ESC, 0)
                time.sleep(2)
                print("Arming ESC now...")
                pi.set_servo_pulsewidth(ESC, min_value)
                time.sleep(1)
                print("See.... uhhhhh")
                control()  # You can change this to any other function you want
    except Exception as e:
        print(f"Error during calibration: {e}")


def control():
    if not IS_RPI:
        print("Control not possible: pigpio not initialized.")
        return
    print("I'm Starting the motor, I hope its calibrated and armed, if not restart by giving 'x'")
    time.sleep(1)
    speed = 1500  # change your speed if you want to.... it should be between 700 - 2000
    print("Controls - a to decrease speed & d to increase speed OR q to decrease a lot of speed & e to increase a lot of speed")
    while True:
        try:
            pi.set_servo_pulsewidth(ESC, speed)
        except Exception as e:
            print(f"Error setting speed: {e}")
            break
        inp = input()

        if inp == "q":
            speed -= 100  # decrementing the speed like hell
            print("speed = %d" % speed)
        elif inp == "e":
            speed += 100  # incrementing the speed like hell
            print("speed = %d" % speed)
        elif inp == "d":
            speed += 10  # incrementing the speed
            print("speed = %d" % speed)
        elif inp == "a":
            speed -= 10  # decrementing the speed
            print("speed = %d" % speed)
        elif inp == "stop":
            stop()  # going for the stop function
            break
        elif inp == "manual":
            manual_drive()
            break
        elif inp == "arm":
            arm()
            break
        else:
            print("WHAT DID I SAID!! Press a,q,d or e")


def arm():  # This is the arming procedure of an ESC
    if not IS_RPI:
        print("Arming not possible: pigpio not initialized.")
        return
    print("Connect the battery and press Enter")
    inp = input()
    if inp == '':
        try:
            pi.set_servo_pulsewidth(ESC, 0)
            time.sleep(1)
            pi.set_servo_pulsewidth(ESC, max_value)
            time.sleep(1)
            pi.set_servo_pulsewidth(ESC, min_value)
            time.sleep(1)
            control()
        except Exception as e:
            print(f"Error during arming: {e}")


def stop():  # This will stop every action your Pi is performing for ESC ofcourse.
    if not IS_RPI:
        print("Stopping not possible: pigpio not initialized.")
        return
    if pi:
        try:
            pi.set_servo_pulsewidth(ESC, 0)
            pi.stop()
        except Exception as e:
            print(f"Error during stopping: {e}")


@app.route('/api/test', methods=['GET'])
def test_api():
    return jsonify({'message': 'API is working'})


@app.route('/api/system/info', methods=['GET'])
def get_system_info():
    cpu_temperature = os.popen("vcgencmd measure_temp").readline().replace("temp=", "").replace("'C\\n", "")
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
        # On verifie que le content type est bien celui attendu.
        if 'multipart/x-mixed-replace' in response.headers['Content-Type']:
            return jsonify({'status': 'OK', 'message': 'Stream is available'})
        else:
            return jsonify({'status': 'Error', 'message': 'Unexpected content type'}), 500

    except requests.exceptions.RequestException as e:
        return jsonify({'status': 'Error', 'message': f'Stream unavailable: {e}'}), 500


# This is the start of the program actually, to start the function it needs to be initialized before calling... stupid python.
if __name__ == '__main__':
    try:
        app.run(debug=True, host='0.0.0.0', port=5000)
    finally:
        if pi:
            stop()
import os
import time
from flask import Flask, jsonify
from flask_cors import CORS
import psutil
import requests

app = Flask(__name__)
CORS(app)

ESC = 18  # Connect the ESC in this GPIO pin

# Initialize pigpio
IS_RPI = False
pi = None
try:
    import pigpio  # Importing GPIO library
    pi = pigpio.pi()
    if not pi.connected:
        print("Can't connect to pigpio daemon. Is it running?")
        pi = None
    else:
        pi.set_servo_pulsewidth(ESC, 0)
        IS_RPI = True
except ImportError:
    print("pigpio library not found. Please install it.")
except Exception as e:
    print(f"Error initializing pigpio: {e}")

if not IS_RPI:
    print("ESC control functions are disabled.")

max_value = 2000  # change this if your ESC's max value is different or leave it be
min_value = 700  # change this if your ESC's min value is different or leave it be

print("For first time launch, select calibrate")
print("Type the exact word for the function you want")
print("calibrate OR manual OR control OR arm OR stop")


def manual_drive():  # You will use this function to program your ESC if required
    if not IS_RPI:
        print("Manual drive not possible: pigpio not initialized.")
        return
    print("You have selected manual option so give a value between 0 and you max value")
    while True:
        inp = input()
        if inp == "stop":
            stop()
            break
        elif inp == "control":
            control()
            break
        elif inp == "arm":
            arm()
            break
        else:
            try:
                pi.set_servo_pulsewidth(ESC, int(inp))
            except ValueError:
                print("Invalid input. Please enter a number or 'stop'.")


def calibrate():  # This is the auto calibration procedure of a normal ESC
    if not IS_RPI:
        print("Calibration not possible: pigpio not initialized.")
        return
    pi.set_servo_pulsewidth(ESC, 0)
    print("Disconnect the battery and press Enter")
    inp = input()
    if inp == '':
        pi.set_servo_pulsewidth(ESC, max_value)
        print("Connect the battery NOW.. you will here two beeps, then wait for a gradual falling tone then press Enter")
        inp = input()
        if inp == '':
            pi.set_servo_pulsewidth(ESC, min_value)
            print("Wierd eh! Special tone")
            time.sleep(7)
            print("Wait for it ....")
            time.sleep(5)
            print("Im working on it, DONT WORRY JUST WAIT.....")
            pi.set_servo_pulsewidth(ESC, 0)
            time.sleep(2)
            print("Arming ESC now...")
            pi.set_servo_pulsewidth(ESC, min_value)
            time.sleep(1)
            print("See.... uhhhhh")
            control()  # You can change this to any other function you want


def control():
    if not IS_RPI:
        print("Control not possible: pigpio not initialized.")
        return
    print("I'm Starting the motor, I hope its calibrated and armed, if not restart by giving 'x'")
    time.sleep(1)
    speed = 1500  # change your speed if you want to.... it should be between 700 - 2000
    print("Controls - a to decrease speed & d to increase speed OR q to decrease a lot of speed & e to increase a lot of speed")
    while True:
        pi.set_servo_pulsewidth(ESC, speed)
        inp = input()

        if inp == "q":
            speed -= 100  # decrementing the speed like hell
            print("speed = %d" % speed)
        elif inp == "e":
            speed += 100  # incrementing the speed like hell
            print("speed = %d" % speed)
        elif inp == "d":
            speed += 10  # incrementing the speed
            print("speed = %d" % speed)
        elif inp == "a":
            speed -= 10  # decrementing the speed
            print("speed = %d" % speed)
        elif inp == "stop":
            stop()  # going for the stop function
            break
        elif inp == "manual":
            manual_drive()
            break
        elif inp == "arm":
            arm()
            break
        else:
            print("WHAT DID I SAID!! Press a,q,d or e")


def arm():  # This is the arming procedure of an ESC
    if not IS_RPI:
        print("Arming not possible: pigpio not initialized.")
        return
    print("Connect the battery and press Enter")
    inp = input()
    if inp == '':
        pi.set_servo_pulsewidth(ESC, 0)
        time.sleep(1)
        pi.set_servo_pulsewidth(ESC, max_value)
        time.sleep(1)
        pi.set_servo_pulsewidth(ESC, min_value)
        time.sleep(1)
        control()


def stop():  # This will stop every action your Pi is performing for ESC ofcourse.
    if not IS_RPI:
        print("Stopping not possible: pigpio not initialized.")
        return
    if pi:
        pi.set_servo_pulsewidth(ESC, 0)
        pi.stop()


@app.route('/api/test', methods=['GET'])
def test_api():
    return jsonify({'message': 'API is working'})


@app.route('/api/system/info', methods=['GET'])
def get_system_info():
    cpu_temperature = os.popen("vcgencmd measure_temp").readline().replace("temp=", "").replace("'C\\n", "")
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
        # On verifie que le content type est bien celui attendu.
        if 'multipart/x-mixed-replace' in response.headers['Content-Type']:
            return jsonify({'status': 'OK', 'message': 'Stream is available'})
        else:
            return jsonify({'status': 'Error', 'message': 'Unexpected content type'}), 500

    except requests.exceptions.RequestException as e:
        return jsonify({'status': 'Error', 'message': f'Stream unavailable: {e}'}), 500


# This is the start of the program actually, to start the function it needs to be initialized before calling... stupid python.
if __name__ == '__main__':
    try:
        app.run(debug=True, host='0.0.0.0', port=5000)
    finally:
        if pi:
            stop()
import os
import time
from flask import Flask, jsonify
from flask_cors import CORS
import psutil
import requests

app = Flask(__name__)
CORS(app)

ESC = 18  # Connect the ESC in this GPIO pin

# Initialize pigpio
try:
    os.system("sudo pigpiod")  # Launching GPIO library
    time.sleep(1)  # Wait for pigpiod to start
    import pigpio  # Importing GPIO library
    pi = pigpio.pi()
    pi.set_servo_pulsewidth(ESC, 0)
    IS_RPI = True
except Exception as e:
    print(f"Error initializing pigpio: {e}")
    pi = None
    IS_RPI = False

max_value = 2000  # change this if your ESC's max value is different or leave it be
min_value = 700  # change this if your ESC's min value is different or leave it be

print("For first time launch, select calibrate")
print("Type the exact word for the function you want")
print("calibrate OR manual OR control OR arm OR stop")


def manual_drive():  # You will use this function to program your ESC if required
    print("You have selected manual option so give a value between 0 and you max value")
    while True:
        inp = input()
        if inp == "stop":
            stop()
            break
        elif inp == "control":
            control()
            break
        elif inp == "arm":
            arm()
            break
        else:
            try:
                pi.set_servo_pulsewidth(ESC, int(inp))
            except ValueError:
                print("Invalid input. Please enter a number or 'stop'.")


def calibrate():  # This is the auto calibration procedure of a normal ESC
    if not IS_RPI:
        print("Calibration not possible: Not running on Raspberry Pi")
        return
    pi.set_servo_pulsewidth(ESC, 0)
    print("Disconnect the battery and press Enter")
    inp = input()
    if inp == '':
        pi.set_servo_pulsewidth(ESC, max_value)
        print("Connect the battery NOW.. you will here two beeps, then wait for a gradual falling tone then press Enter")
        inp = input()
        if inp == '':
            pi.set_servo_pulsewidth(ESC, min_value)
            print("Wierd eh! Special tone")
            time.sleep(7)
            print("Wait for it ....")
            time.sleep(5)
            print("Im working on it, DONT WORRY JUST WAIT.....")
            pi.set_servo_pulsewidth(ESC, 0)
            time.sleep(2)
            print("Arming ESC now...")
            pi.set_servo_pulsewidth(ESC, min_value)
            time.sleep(1)
            print("See.... uhhhhh")
            control()  # You can change this to any other function you want


def control():
    if not IS_RPI:
        print("Control not possible: Not running on Raspberry Pi")
        return
    print("I'm Starting the motor, I hope its calibrated and armed, if not restart by giving 'x'")
    time.sleep(1)
    speed = 1500  # change your speed if you want to.... it should be between 700 - 2000
    print("Controls - a to decrease speed & d to increase speed OR q to decrease a lot of speed & e to increase a lot of speed")
    while True:
        pi.set_servo_pulsewidth(ESC, speed)
        inp = input()

        if inp == "q":
            speed -= 100  # decrementing the speed like hell
            print("speed = %d" % speed)
        elif inp == "e":
            speed += 100  # incrementing the speed like hell
            print("speed = %d" % speed)
        elif inp == "d":
            speed += 10  # incrementing the speed
            print("speed = %d" % speed)
        elif inp == "a":
            speed -= 10  # decrementing the speed
            print("speed = %d" % speed)
        elif inp == "stop":
            stop()  # going for the stop function
            break
        elif inp == "manual":
            manual_drive()
            break
        elif inp == "arm":
            arm()
            break
        else:
            print("WHAT DID I SAID!! Press a,q,d or e")


def arm():  # This is the arming procedure of an ESC
    if not IS_RPI:
        print("Arming not possible: Not running on Raspberry Pi")
        return
    print("Connect the battery and press Enter")
    inp = input()
    if inp == '':
        pi.set_servo_pulsewidth(ESC, 0)
        time.sleep(1)
        pi.set_servo_pulsewidth(ESC, max_value)
        time.sleep(1)
        pi.set_servo_pulsewidth(ESC, min_value)
        time.sleep(1)
        control()


def stop():  # This will stop every action your Pi is performing for ESC ofcourse.
    if not IS_RPI:
        print("Stopping not possible: Not running on Raspberry Pi")
        return
    pi.set_servo_pulsewidth(ESC, 0)
    pi.stop()


@app.route('/api/test', methods=['GET'])
def test_api():
    return jsonify({'message': 'API is working'})


@app.route('/api/system/info', methods=['GET'])
def get_system_info():
    cpu_temperature = os.popen("vcgencmd measure_temp").readline().replace("temp=", "").replace("'C\\n", "")
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
        # On verifie que le content type est bien celui attendu.
        if 'multipart/x-mixed-replace' in response.headers['Content-Type']:
            return jsonify({'status': 'OK', 'message': 'Stream is available'})
        else:
            return jsonify({'status': 'Error', 'message': 'Unexpected content type'}), 500

    except requests.exceptions.RequestException as e:
        return jsonify({'status': 'Error', 'message': f'Stream unavailable: {e}'}), 500


# This is the start of the program actually, to start the function it needs to be initialized before calling... stupid python.
if __name__ == '__main__':
    if IS_RPI:
        inp = input()
        if inp == "manual":
            manual_drive()
        elif inp == "calibrate":
            calibrate()
        elif inp == "arm":
            arm()
        elif inp == "control":
            control()
        elif inp == "stop":
            stop()
        else:
            print("Thank You for not following the things I'm saying... now you gotta restart the program STUPID!!")
    try:
        app.run(debug=True, host='0.0.0.0', port=5000)
    finally:
        if IS_RPI and pi:
            pi.stop()
