import os
import sys
import bpy
import json
import time
import random
import threading
import subprocess
from bpy.props import StringProperty


# Read Inputs
#########################################

external_port = os.environ["DEBUGGER_PORT"]
pip_path = os.environ["PIP_PATH"]
external_addon_directory = os.environ['ADDON_DEV_DIR']

python_path = bpy.app.binary_path_python
external_url = f"http://localhost:{external_port}"


# Install Required Packages
##########################################

try: import pip
except ModuleNotFoundError:
    subprocess.run([python_path, pip_path])

def install_package(name):
    subprocess.run([python_path, "-m", "pip", "install", name])

def get_package(name):
    try: return __import__(name)
    except ModuleNotFoundError:
        install_package(name)
        return __import__(name)

ptvsd = get_package("ptvsd")
flask = get_package("flask")
requests = get_package("requests")


# Setup Communication
#########################################

def start_blender_server():
    from flask import Flask, jsonify

    port = [None]

    def server_thread_function():
        app = Flask("Blender Server")
        @app.route("/", methods=['POST'])
        def handle_post():
            data = flask.request.get_json()
            print("Got POST:", data)
            if data["type"] == "update":
                bpy.ops.dev.update_addon(module_name=addon_folder_name)
            return "OK"

        while True:
            try:
                port[0] = get_random_port()
                app.run(debug=True, port=port[0], use_reloader=False)
            except OSError:
                pass

    thread = threading.Thread(target=server_thread_function)
    thread.daemon = True
    thread.start()

    while port[0] is None:
        print("sleep")
        time.sleep(0.01)

    return port[0]

def start_debug_server():
    while True:
        port = get_random_port()
        try:
            ptvsd.enable_attach(("localhost", port))
            break
        except OSError:
            pass
    return port

def get_random_port():
    return random.randint(2000, 10000)

def send_connection_information(blender_port, debug_port):
    data = {
        "type" : "setup",
        "blenderPort" : blender_port,
        "debugPort" : debug_port,
    }
    print(data)
    requests.post(external_url, json=data)

blender_port = start_blender_server()
debug_port = start_debug_server()
send_connection_information(blender_port, debug_port)

print("Waiting for debug client.")
ptvsd.wait_for_attach()
print("Debug cliend attached.")


# Load Addon
########################################

addon_directory = bpy.utils.user_resource('SCRIPTS', "addons")
addon_folder_name = os.path.basename(external_addon_directory)
symlink_path = os.path.join(addon_directory, addon_folder_name)

if not os.path.exists(addon_directory):
    os.makedirs(addon_directory)
if os.path.exists(symlink_path):
    os.remove(symlink_path)

os.symlink(external_addon_directory, symlink_path, target_is_directory=True)

bpy.ops.wm.addon_enable(module=addon_folder_name)


# Operators
########################################

class UpdateAddonOperator(bpy.types.Operator):
    bl_idname = "dev.update_addon"
    bl_label = "Update Addon"

    module_name: StringProperty()

    def execute(self, context):
        bpy.ops.wm.addon_disable(module=self.module_name)

        for name in list(sys.modules.keys()):
            if name.startswith(self.module_name):
                del sys.modules[name]

        bpy.ops.wm.addon_enable(module=self.module_name)

        self.redraw_all(context)
        return {'FINISHED'}

    def redraw_all(self, context):
        for window in context.window_manager.windows:
            for area in window.screen.areas:
                area.tag_redraw()

bpy.utils.register_class(UpdateAddonOperator)