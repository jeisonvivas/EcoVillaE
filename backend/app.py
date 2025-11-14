# backend/app.py - EcoVilla listo para Vercel
from flask import Flask, request, jsonify, render_template, send_from_directory
from flask_cors import CORS
from db import get_connection
from datetime import datetime
import os

# Configuración Flask
app = Flask(__name__, template_folder="../templates", static_folder="../static")
CORS(app)

# -------------------
# Puntos por kg
# -------------------
POINTS_PER_KG = {
    "plastico": 10, "plástico": 10, "papel": 8, "vidrio": 5,
    "metal": 12, "orgánico": 4, "organico": 4, "otros": 1
}

def compute_points(material, cantidad):
    if not material: return 0
    m = material.strip().lower()
    pts_per = POINTS_PER_KG.get(m, POINTS_PER_KG.get(m.replace("á","a"), 1))
    try: q = float(cantidad)
    except: q = 0
    return int(q * pts_per)

# -------------------
# Rutas Frontend
# -------------------
@app.route("/")
def home(): return render_template("index.html")

@app.route("/login")
def login_page(): return render_template("login.html")

@app.route("/registrar")
def registrar_page(): return render_template("registrar.html")

@app.route('/static/<path:path>')
def send_static(path):
    return send_from_directory("../static", path)

# -------------------
# API: Status
# -------------------
@app.get("/status")
def status(): return {"status":"ok"}

# -------------------
# API: REGISTER
# -------------------
@app.post("/register")
def register():
    data = request.json or {}
    nombre = data.get("nombre")
    email = data.get("email")
    contraseña = data.get("contraseña")
    telefono = data.get("telefono")
    numero_identificacion = data.get("numero_identificacion")

    if not nombre or not email or not contraseña:
        return jsonify({"error": "nombre, email y contraseña son requeridos"}), 400

    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id FROM usuario WHERE email = %s", (email,))
    if cur.fetchone():
        cur.close(); conn.close()
        return jsonify({"error":"email ya registrado"}), 400

    cur.execute("""
        INSERT INTO usuario (nombre, email, contraseña, telefono, numero_identificacion)
        VALUES (%s, %s, %s, %s, %s) RETURNING id
    """, (nombre, email, contraseña, telefono, numero_identificacion))
    new_id = cur.fetchone()[0]
    conn.commit()
    cur.close(); conn.close()
    return jsonify({"id": new_id, "nombre": nombre, "email": email})

# -------------------
# API: LOGIN
# -------------------
@app.post("/login")
def login():
    data = request.json or {}
    email = data.get("email")
    contraseña = data.get("contraseña")
    if not email or not contraseña:
        return jsonify({"error":"email y contraseña son requeridos"}), 400

    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, nombre FROM usuario WHERE email = %s AND contraseña = %s", (email, contraseña))
    row = cur.fetchone()
    cur.close(); conn.close()
    if not row: return jsonify({"error":"credenciales invalidas"}), 401
    return jsonify({"id": row[0], "nombre": row[1], "email": email})

# -------------------
# API: Buscar usuario
# -------------------
@app.get("/buscar_usuario")
def buscar_usuario():
    q = request.args.get("q","").strip()
    if not q: return jsonify([])
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, nombre, numero_identificacion
        FROM usuario
        WHERE nombre ILIKE %s OR numero_identificacion ILIKE %s OR CAST(id AS TEXT) = %s
        ORDER BY nombre LIMIT 20
    """, (f"%{q}%", f"%{q}%", q))
    rows = cur.fetchall()
    cur.close(); conn.close()
    return jsonify([{"id": r[0], "nombre": r[1], "documento": r[2]} for r in rows])

# -------------------
# API: Usuarios y detalle
# -------------------
@app.get("/usuarios")
def usuarios():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, nombre, numero_identificacion FROM usuario ORDER BY id")
    rows = cur.fetchall()
    cur.close(); conn.close()
    return jsonify([{"id":r[0],"nombre":r[1],"documento":r[2]} for r in rows])

@app.get("/usuario/<int:uid>")
def usuario_detail(uid):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, nombre, email, telefono, numero_identificacion FROM usuario WHERE id = %s", (uid,))
    r = cur.fetchone()
    if not r: cur.close(); conn.close(); return jsonify({"error":"usuario no encontrado"}), 404

    cur.execute("SELECT material, cantidad FROM reciclaje WHERE usuarioid = %s", (uid,))
    rows = cur.fetchall()
    total_points, total_kg = 0, 0
    for mat, qty in rows:
        total_points += compute_points(mat, qty)
        try: total_kg += float(qty)
        except: pass
    cur.close(); conn.close()
    return jsonify({
        "id": r[0], "nombre": r[1], "email": r[2], "telefono": r[3],
        "numero_identificacion": r[4], "total_points": total_points, "total_kg": total_kg
    })

# -------------------
# API: Reciclaje
# -------------------
@app.get("/reciclaje")
def get_reciclaje():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, usuarioid, material, fecha, cantidad FROM reciclaje ORDER BY fecha DESC NULLS LAST")
    rows = cur.fetchall()
    cur.close(); conn.close()
    return jsonify([{
        "id": r[0], "usuarioid": r[1], "material": r[2],
        "fecha": str(r[3]) if r[3] else None,
        "cantidad": float(r[4]) if r[4] else 0
    } for r in rows])

@app.post("/reciclaje")
def post_reciclaje():
    data = request.json or {}
    usuarioid = data.get("usuarioid")
    material = data.get("material")
    cantidad = data.get("cantidad")
    if not usuarioid or not material or cantidad is None:
        return jsonify({"error":"usuarioid, material y cantidad requeridos"}), 400

    fecha = datetime.now().isoformat(sep=' ')
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("INSERT INTO reciclaje (usuarioid, material, fecha, cantidad) VALUES (%s, %s, %s, %s) RETURNING id",
                (usuarioid, material, fecha, cantidad))
    new_id = cur.fetchone()[0]
    conn.commit()
    cur.close(); conn.close()
    points = compute_points(material, cantidad)
    return jsonify({"id": new_id, "points": points})

# -------------------
# API: Ranking
# -------------------
@app.get("/ranking")
def get_ranking():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT usuarioid, material, SUM(cantidad) FROM reciclaje GROUP BY usuarioid, material")
    rows = cur.fetchall()
    agg = {}
    for uid, mat, s in rows: agg[uid] = agg.get(uid, 0) + compute_points(mat, s)
    cur.execute("SELECT id, nombre FROM usuario")
    users = {r[0]: r[1] for r in cur.fetchall()}
    cur.close(); conn.close()
    data = [{"usuarioid": uid, "nombre": users.get(uid, f"Usuario {uid}"), "points": pts} for uid, pts in agg.items()]
    data.sort(key=lambda x: x["points"], reverse=True)
    return jsonify(data)

# -------------------
# Run local / Vercel
# -------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
