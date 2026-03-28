# =============================================================================
# [AUTO-INJECTED] Scene Preload & Wait Logic
# =============================================================================
import sys
import argparse
import socket
import json

# Only execute the wait logic if we are running the script directly
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--wait", action="store_true", help="Wait for START signal via UDP")
    parser.add_argument("--port", type=int, default=0, help="UDP port to listen on for START signal")
    # Parse known args so we don't crash if other args are passed
    args, _ = parser.parse_known_args()

    if args.wait and args.port > 0:
        print(f"[Scene] Started in PRELOAD mode. Waiting for START command on port {args.port}...")
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("127.0.0.1", args.port))
        sock.settimeout(None) # Wait indefinitely
        
        while True:
            data, addr = sock.recvfrom(1024)
            try:
                msg = json.loads(data.decode('utf-8'))
                if msg.get("cmd") == "START":
                    print("[Scene] Received START command. Booting up...")
                    sock.close()
                    break
            except Exception as e:
                pass
# =============================================================================
import pygfx as gfx
from rendercanvas.auto import RenderCanvas, loop
import numpy as np

canvas = RenderCanvas(size=(640, 480))
renderer = gfx.renderers.WgpuRenderer(canvas)
scene = gfx.Scene()

camera = gfx.PerspectiveCamera(70, 16/9)
camera.local.z = 400

geo1 = gfx.plane_geometry(200, 200, 10, 10)
colors1 = np.ones((geo1.positions.nitems, 4), dtype=np.float32)
colors1[:, 3] = 0.5 # semi transparent
geo1.colors = gfx.Buffer(colors1)

# Enable transparent pass via material.opacity or color mode
mat1 = gfx.MeshBasicMaterial(color_mode="vertex")
mesh1 = gfx.Mesh(geo1, mat1)
mesh1.local.z = 100
scene.add(mesh1)

geo2 = gfx.plane_geometry(200, 200, 1, 1)
mesh2 = gfx.Mesh(geo2, gfx.MeshBasicMaterial(color=(1,0,0,1)))
mesh2.local.z = 0
scene.add(mesh2)

def animate():
    try:
        renderer.render(scene, camera)
    except RuntimeError:
        pass
    canvas.request_draw()
    loop.stop()

canvas.request_draw(animate)
loop.run()
print("Success")
