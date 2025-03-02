from flask import Flask, jsonify, render_template, request
import os
import subprocess
import psutil
import time
import threading
import socket

app = Flask(__name__)

# --- Global variables for system info and ping ---
system_info_cache = {}
last_system_info_update = 0
system_info_update_interval = 5  # seconds

ping_results_cache = {}
last_ping_time = {}
ping_update_interval = 10 # seconds


# --- Helper functions ---

def get_cpu_temperature():
    """Gets the CPU temperature from the system."""
    try:
        with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
            temp = int(f.read()) / 1000.0
            return temp
    except FileNotFoundError:
        return "N/A (File not found)"
    except Exception as e:
        return f"Error: {e}"

def get_cpu_usage():
    """Gets the CPU usage percentage."""
    return psutil.cpu_percent(interval=1)

def get_memory_usage():
    """Gets the memory usage information."""
    memory = psutil.virtual_memory()
    return {
        "total": memory.total,
        "available": memory.available,
        "percent": memory.percent,
        "used": memory.used,
        "free": memory.free,
    }

def get_system_info():
    """Gets the current system information."""
    global last_system_info_update, system_info_cache
    if time.time() - last_system_info_update > system_info_update_interval:
        system_info_cache = {
            "cpu_temperature": get_cpu_temperature(),
            "cpu_usage": get_cpu_usage(),
            "memory_usage": get_memory_usage(),
            "timestamp": time.time()
        }
        last_system_info_update = time.time()
    return system_info_cache

def ping_ip(ip_address):
    """Pings the given IP address and returns the result."""
    try:
        response = subprocess.check_output(
            ["ping", "-c", "1", ip_address], stderr=subprocess.STDOUT, timeout=5
        ).decode("utf-8")
        
        # Extract ping time from output
        if "time=" in response:
            start_index = response.find("time=") + 5
            end_index = response.find(" ms", start_index)
            ping_time = float(response[start_index:end_index])
        else :
            ping_time = None
           
        if "1 received" in response :
            status = "OK"
        else:
            status = "KO"

        return {
            "ip_address": ip_address,
            "status": status,
            "ping_time_ms": ping_time,
            "timestamp": time.time()
        }
    except subprocess.CalledProcessError as e:
        return {
            "ip_address": ip_address,
            "status": "KO",
            "error": str(e),
            "timestamp": time.time()
        }
    except subprocess.TimeoutExpired as e:
      return {
          "ip_address": ip_address,
          "status": "Timeout",
          "error": str(e),
          "timestamp": time.time()
      }
    except Exception as e:
      return {
          "ip_address": ip_address,
          "status": "Error",
          "error": str(e),
          "timestamp": time.time()
      }

def update_ping_results(ip_address):
    global ping_results_cache, last_ping_time
    if ip_address not in last_ping_time or time.time() - last_ping_time[ip_address] > ping_update_interval:
        ping_results_cache[ip_address] = ping_ip(ip_address)
        last_ping_time[ip_address] = time.time()

def validate_ip_address(ip):
  """valid ip for ping"""
  try:
      socket.inet_aton(ip)
      return True
  except socket.error:
      return False
# --- Routes ---

# Route pour la page d'accueil (sert index.html)
@app.route("/")
def index():
    return render_template("index.html")

# Route API pour le test
@app.route("/api/test")
def api_test():
    return jsonify({"message": "L'API fonctionne!"})

# Route pour obtenir les informations système
@app.route("/api/system_info")
def api_system_info():
    system_info = get_system_info()
    return jsonify(system_info)

# Route pour lancer un ping vers une IP donnée
@app.route("/api/ping/<ip_address>")
def api_ping(ip_address):
    if not validate_ip_address(ip_address):
        return jsonify({"error": "Invalid IP address"}), 400

    update_ping_results(ip_address)
    return jsonify(ping_results_cache.get(ip_address))

# Route pour demander un ping d'une addresse ip
@app.route("/api/ping", methods=["POST"])
def api_ping_post():
    data = request.get_json()
    if not data or "ip_address" not in data:
        return jsonify({"error": "Missing 'ip_address' in request body"}), 400
    ip_address = data["ip_address"]
    if not validate_ip_address(ip_address):
        return jsonify({"error": "Invalid IP address"}), 400
    update_ping_results(ip_address)
    return jsonify(ping_results_cache.get(ip_address))

# Route pour le future control gpio (a implementer)
# @app.route("/api/gpio/<int:pin>/<int:state>")
# def control_gpio(pin, state):
#     # Code pour contrôler le GPIO ...
#     return jsonify({"status": "OK", "pin": pin, "state": state})

# --- Main ---

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
