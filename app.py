from flask import Flask, render_template_string, request
import paho.mqtt.client as mqtt

app = Flask(__name__)

mqtt_broker = "serveo.net"
mqtt_port = 1111
mqtt_topic = "led/control"

mqtt_client = mqtt.Client()
mqtt_client.connect(mqtt_broker, mqtt_port, 60)

# HTML Template
html = """
<!doctype html>
<title>LED Controller</title>
<h2>Control NodeMCU LED</h2>
<form method="POST">
    <button name="led" value="ON">Turn ON</button>
    <button name="led" value="OFF">Turn OFF</button>
</form>
"""

@app.route("/", methods=["GET", "POST"])
def control_led():
    if request.method == "POST":
        action = request.form["led"]
        mqtt_client.publish(mqtt_topic, action)
        return f"<p>LED turned {action}</p><a href='/'>Go back</a>"
    return render_template_string(html)

if __name__ == "__main__":
    app.run(debug=True)
