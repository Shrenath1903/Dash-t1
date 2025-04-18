from flask import Flask, render_template, redirect, url_for, jsonify, request
from paho.mqtt import client as mqtt_client
import logging
import time
import threading
from datetime import datetime
import signal
import sys

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# MQTT Server settings - Updated to match ESP8266 code
MQTT_BROKER = "serveo.net"
MQTT_PORT = 12346


# Flask app initialization
app = Flask(__name__)

# Global state tracking for both locations
device_state = {
    "office": {
        "device_connected": False,
        "last_seen": 0
    },
    "home": {
        "device_connected": False,
        "last_seen": 0
    },
    "mqtt_connected": False
}

# Sensor data storage for both locations
sensor_data = {
    "office": {
        "temp": 0,
        "humidity": 0,
        "d0": "0",  # Digital input 1
        "d1": "OFF",  # Switch 1
        "d2": "0",  # Digital input 2
        "d3": "OFF",  # Switch 2
        "output_d5": "OFF",  # Digital output 1
        "output_d6": "OFF",  # Digital output 2
        "output_d7": "OFF",  # LED control
        "led_d7": 0  # LED brightness (0-100)
    },
    "home": {
        "temp": 0,
        "humidity": 0,
        "d0": "0",
        "d1": "OFF",
        "d2": "0",
        "d3": "OFF",
        "output_d5": "OFF",
        "output_d6": "OFF",
        "output_d7": "OFF",
        "led_d7": 0
    }
}

# History data for both locations
history_data = {
    "office": {
        "temp_history": [],
        "humidity_history": [],
        "timestamps": []
    },
    "home": {
        "temp_history": [],
        "humidity_history": [],
        "timestamps": []
    }
}

# Keep history limited to points
MAX_HISTORY_POINTS = 20

# MQTT callbacks
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        logger.info("Connected to MQTT broker")
        device_state["mqtt_connected"] = True
        
        # Updated topics to match ESP8266 code structure
        client.subscribe([
            # Device connection
            ("device/connection", 1),
            # General control topics
            ("control/#", 1),
            # Sensor topics
            ("sensor/#", 1),
            # Test topic
            ("test/topic", 1)
        ])
    else:
        logger.error(f"Failed to connect to MQTT broker with result code {rc}")
        device_state["mqtt_connected"] = False

def on_disconnect(client, userdata, rc):
    logger.warning("Disconnected from MQTT broker")
    device_state["mqtt_connected"] = False

def on_message(client, userdata, msg):
    topic = msg.topic
    payload = msg.payload.decode()
    logger.info(f"Message received on {topic}: {payload}")
    
    # Set default location (since ESP doesn't specify location prefixes)
    location = "office"  # Default to office for compatibility
    
    # Update device connection timestamp
    device_state[location]["last_seen"] = time.time()
    device_state[location]["device_connected"] = True
    
    # Handle control topics
    if "control" in topic:
        control_type = topic.split('/')[-1]  # e.g., "output_d5"
        
        if control_type in sensor_data[location]:
            sensor_data[location][control_type] = payload
            
            # For LED brightness control
            if control_type == "led_d7":
                try:
                    sensor_data[location]["led_d7"] = int(payload)
                except ValueError:
                    logger.error(f"Invalid LED value: {payload}")
    
    # Handle sensor topics
    elif "sensor" in topic:
        sensor_type = topic.split('/')[-1]  # e.g., "d0"
        
        if sensor_type in ["d0", "d1", "d2", "d3"]:
            sensor_data[location][sensor_type] = payload
    
    # Handle connection status updates
    elif "device/connection" == topic:
        if payload == "ONLINE":
            device_state[location]["device_connected"] = True
        elif payload == "OFFLINE":
            device_state[location]["device_connected"] = False

# Connection monitoring thread
def connection_monitor():
    while True:
        current_time = time.time()
        # Check both locations
        for location in ["office", "home"]:
            if device_state[location]["device_connected"] and current_time - device_state[location]["last_seen"] > 30:
                device_state[location]["device_connected"] = False
                logger.warning(f"{location.capitalize()} device connection timed out")
        time.sleep(5)

# MQTT client instance
client = mqtt_client.Client(mqtt_client.CallbackAPIVersion.VERSION2, client_id="iot_dashboard")
client.on_connect = on_connect
client.on_message = on_message
client.on_disconnect = on_disconnect

# Remove TLS and auth since the ESP code doesn't use it
# client.tls_set()
# client.username_pw_set(MQTT_USER, MQTT_PASSWORD)

# Set last will message
client.will_set("device/connection", "OFFLINE", qos=1, retain=True)

try:
    client.connect(MQTT_BROKER, MQTT_PORT, 60)
    client.loop_start()
    monitor_thread = threading.Thread(target=connection_monitor, daemon=True)
    monitor_thread.start()
except Exception as e:
    logger.error(f"Failed to connect to MQTT broker: {e}")

# Flask Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/dashboard')
def dashboard():
    return render_template('dashboard.html')

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/products')
def products():
    return render_template('products.html')

@app.route('/contact')
def contact():
    return render_template('contact.html')
# API route for all data
@app.route('/get_data')
def get_data():
    data = {
        "office": {
            "sensor_data": sensor_data["office"],
            "temp_history": history_data["office"]["temp_history"],
            "humidity_history": history_data["office"]["humidity_history"],
            "timestamps": history_data["office"]["timestamps"],
            "device_connected": device_state["office"]["device_connected"]
        },
        "home": {
            "sensor_data": sensor_data["home"],
            "temp_history": history_data["home"]["temp_history"],
            "humidity_history": history_data["home"]["humidity_history"],
            "timestamps": history_data["home"]["timestamps"],
            "device_connected": device_state["home"]["device_connected"]
        },
        "mqtt_connected": device_state["mqtt_connected"]
    }
    return jsonify(data)

# API route for single location data
@app.route('/get_location_data/<location>')
def get_location_data(location):
    if location not in ["office", "home"]:
        return jsonify({"error": "Invalid location"}), 400
    
    data = {
        "sensor_data": sensor_data[location],
        "temp_history": history_data[location]["temp_history"],
        "humidity_history": history_data[location]["humidity_history"],
        "timestamps": history_data[location]["timestamps"],
        "device_connected": device_state[location]["device_connected"],
        "mqtt_connected": device_state["mqtt_connected"]
    }
    return jsonify(data)

# Control endpoint for both locations
@app.route('/control', methods=['POST'])
def control():
    try:
        data = request.get_json()
        device = data.get('device')      # e.g., "output_d5"
        value = data.get('value')        # e.g., "ON" or "OFF"
        location = data.get('location', 'office')  # Default to office
        
        if not device or value is None:
            return jsonify({"success": False, "error": "Missing device or value"})
        
        # Build the topic - simplified to match ESP8266 expectations
        topic = f"control/{device}"
        
        # Publish to MQTT topic
        client.publish(topic, str(value), qos=1)
        
        # Update local state for immediate UI feedback
        if device in sensor_data[location]:
            sensor_data[location][device] = value
            
        return jsonify({"success": True})
    except Exception as e:
        logger.error(f"Control error: {e}")
        return jsonify({"success": False, "error": str(e)})

# Legacy API endpoint (maintains backward compatibility)
@app.route('/api/sensors')
def get_sensor_data():
    # Default to office for backward compatibility
    return get_location_data("office")

@app.route('/api/status')
def get_status():
    status_data = {
        "office_connected": device_state["office"]["device_connected"],
        "home_connected": device_state["home"]["device_connected"],
        "mqtt_connected": device_state["mqtt_connected"]
    }
    # Add sensor data to the status
    status_data.update({
        "office": sensor_data["office"],
        "home": sensor_data["home"]
    })
    return jsonify(status_data)

# Graceful shutdown on termination
def graceful_shutdown(signum, frame):
    logger.info("Shutting down gracefully...")
    client.publish("device/connection", "OFFLINE", qos=1, retain=True)
    client.disconnect()
    sys.exit(0)

signal.signal(signal.SIGINT, graceful_shutdown)
signal.signal(signal.SIGTERM, graceful_shutdown)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)