"""Always-on alert service. Subscribes to the motor topic and pushes a phone notification
(via ntfy.sh) when a fault appears, current is too high, speed drifts, or data stops.
pip install paho-mqtt requests
Phone: install the free 'ntfy' app, subscribe to NTFY_TOPIC. Run: python alert_backend.py"""
import json, time, threading
import requests
import paho.mqtt.client as mqtt

TOPIC      = "srec-bldc-kavin-7421/telemetry"   # same as everywhere else
NTFY_TOPIC = "srec-bldc-alerts-kavin-7421"      # CHANGE: unique, treat like a password
SETPOINT_RPM, RPM_TOL = 1500, 0.15              # alert if speed off by >15 %
MAX_CURRENT_A         = 3.0                     # set to your motor's limit
OFFLINE_AFTER_S       = 5
COOLDOWN_S            = 30                      # don't spam the same alert

last_seen = time.time(); last_sent = {}; offline = False

def push(key, title, msg, prio="high"):
    if time.time() - last_sent.get(key, 0) < COOLDOWN_S: return
    last_sent[key] = time.time()
    print("ALERT:", title, msg)
    try:
        requests.post(f"https://ntfy.sh/{NTFY_TOPIC}", data=msg.encode(),
                      headers={"Title": title, "Priority": prio, "Tags": "warning"}, timeout=5)
    except Exception as e:
        print("push failed:", e)

def on_message(_c, _u, m):
    global last_seen, offline
    last_seen = time.time()
    if offline:
        offline = False; push("online", "BLDC back online", "Telemetry resumed", "default")
    d = json.loads(m.payload)
    if d["fault"] != "NONE":
        push("fault", f"Hall fault: {d['fault']}", f"rpm={d['rpm']} current={d['current']} A hall={d['hall']}", "urgent")
    if d["current"] > MAX_CURRENT_A:
        push("oc", "Over-current", f"{d['current']} A (limit {MAX_CURRENT_A} A)")
    if abs(d["rpm"] - SETPOINT_RPM) > SETPOINT_RPM * RPM_TOL:
        push("speed", "Speed deviation", f"{d['rpm']} rpm vs setpoint {SETPOINT_RPM}")
    if d["hall"] in ("000", "111"):
        push("hallinv", "Invalid Hall code", f"Hall = {d['hall']}")

def watchdog():
    global offline
    while True:
        time.sleep(1)
        if time.time() - last_seen > OFFLINE_AFTER_S and not offline:
            offline = True; push("offline", "BLDC offline", f"No data for {OFFLINE_AFTER_S}s", "urgent")

c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
c.on_connect = lambda c, *a: c.subscribe(TOPIC)
c.on_message = on_message
c.connect("broker.hivemq.com", 1883)
threading.Thread(target=watchdog, daemon=True).start()
c.loop_forever()
