import os
import json
import random
from datetime import datetime, timedelta
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
import gspread
from google.oauth2.service_account import Credentials

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "quicklan_crm_secret_key_2026")

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

SPREADSHEET_NAME = os.environ.get("SPREADSHEET_NAME", "QuicklandCRM")
SPREADSHEET_ID = os.environ.get("SPREADSHEET_ID", "")

CFG_BASE = {
    "cupo": 150,
    "maxNoContesta": 3,
    "maxCorta": 2,
    "maxSinContacto": 2,
    "diasInteres": 30,
    "diasAgenda": 7,
    "diasRetorno": 2
}

def get_gspread_client():
    creds_json = os.environ.get("GOOGLE_CREDENTIALS_JSON")
    if creds_json:
        creds_info = json.loads(creds_json)
        creds = Credentials.from_service_account_info(creds_info, scopes=SCOPES)
    elif os.path.exists("/etc/secrets/credentials.json"):
        creds = Credentials.from_service_account_file("/etc/secrets/credentials.json", scopes=SCOPES)
    else:
        creds = Credentials.from_service_account_file("credentials.json", scopes=SCOPES)
    return gspread.authorize(creds)

def get_spreadsheet():
    client = get_gspread_client()
    if SPREADSHEET_ID:
        return client.open_by_key(SPREADSHEET_ID)
    return client.open(SPREADSHEET_NAME)

def get_or_create_usuarios_sheet(sh):
    try:
        ws = sh.worksheet("Usuarios")
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title="Usuarios", rows="200", cols="10")
    primera_fila = ws.row_values(1)
    encabezados = ["ID_USUARIO", "NOMBRE_COMPLETO", "USUARIO", "PASSWORD", "ROL", "ESTADO"]
    if not primera_fila:
        ws.update("A1:F1", [encabezados])
    return ws

def get_or_create_base_sheet(sh):
    try:
        ws = sh.worksheet("BASE DE DATOS")
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title="BASE DE DATOS", rows="1000", cols="20")
    
    primera_fila = ws.row_values(1)
    encabezados = [
        "ID", "TIPO", "RUC", "RAZON_SOCIAL", "DNI", "NOMBRE",
        "DISTRITO", "CELULAR", "ESTADO", "ASIGNADO_A", "ULT_USUARIO",
        "INTENTOS", "ULT_TIPIFICACION", "FECHA_AGENDA", "FECHA_VENCE",
        "DISPONIBLE_DESDE", "MOTIVO_OBSERVACION"
    ]
    if not primera_fila:
        ws.update("A1:Q1", [encabezados])
    return ws

def get_or_create_ventas_sheet(sh):
    try:
        ws = sh.worksheet("QuicklandCRM_Ventas")
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title="QuicklandCRM_Ventas", rows="1000", cols="22")

    if ws.col_count < 20:
        ws.add_cols(20 - ws.col_count)

    primera_fila = ws.row_values(1)
    encabezados = [
        "ID_VENTA",                  # A (1)
        "FECHA",                     # B (2)
        "ASESOR",                    # C (3)
        "DNI_RUC",                   # D (4)
        "CLIENTE",                   # E (5)
        "CELULAR",                   # F (6)
        "DISTRITO",                  # G (7)
        "DIRECCION",                 # H (8)
        "COORDENADAS",               # I (9)
        "PLAN",                      # J (10)
        "OBSERVACIONES",             # K (11)
        "ESTADO",                    # L (12)
        "COMENTARIO_BACK",           # M (13)
        "ORIGEN_BASE_ID",            # N (14)
        "CORREO",                    # O (15)
        "NUMERO_RECIBO_CLIENTE",     # P (16)
        "FECHA_VENCIMIENTO_RECIBO",  # Q (17)
        "ESTADO_PAGO_CLIENTE",       # R (18)
        "ESTADO_COMISION",           # S (19)
        "FECHA_PAGO_COMISION"        # T (20)
    ]
    if primera_fila[:20] != encabezados:
        ws.update("A1:T1", [encabezados])
    return ws

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "usuario" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function

# ==========================================================
# LOGIN COMPATIBLE CON FETCH (JSON) Y FORMULARIO HTML
# ==========================================================
@app.route("/", methods=["GET", "POST"])
@app.route("/login", methods=["GET", "POST"])
@app.route("/api/login", methods=["POST"])
@app.route("/auth", methods=["POST"])
def login():
    if request.method == "POST":
        if request.is_json:
            data = request.get_json(silent=True) or {}
        else:
            data = request.form.to_dict()
            if not data:
                data = request.get_json(force=True, silent=True) or {}

        usuario_input = str(
            data.get("usuario") or data.get("username") or data.get("user") or ""
        ).strip()
        password_input = str(
            data.get("password") or data.get("clave") or data.get("pass") or data.get("contraseña") or ""
        ).strip()

        es_ajax = (
            request.is_json
            or request.path in ["/api/login", "/auth"]
            or request.headers.get("X-Requested-With") == "XMLHttpRequest"
            or "application/json" in request.headers.get("Accept", "")
        )

        try:
            sh = get_spreadsheet()
            ws_usuarios = get_or_create_usuarios_sheet(sh)
            usuarios = ws_usuarios.get_all_records()

            for u in usuarios:
                user_db = str(u.get("USUARIO") or u.get("Usuario") or "").strip()
                pass_db = str(u.get("PASSWORD") or u.get("Password") or "").strip()
                nombre_db = str(u.get("NOMBRE_COMPLETO") or u.get("Nombre") or user_db).strip()
                rol_db = str(u.get("ROL") or u.get("Rol") or "VENTAS").strip().upper()
                estado_db = str(u.get("ESTADO") or u.get("Estado") or "Activo").strip().lower()
                id_user_db = str(u.get("ID_USUARIO") or "").strip()

                if user_db.lower() == usuario_input.lower() and pass_db == password_input:
                    if estado_db not in ["activo", "1", "true", "si", "sí", ""]:
                        msg = "Tu usuario está Inactivo. Comunícate con el Administrador."
                        if es_ajax or request.data:
                            return jsonify({
                                "ok": False,
                                "success": False,
                                "status": "error",
                                "error": msg,
                                "msg": msg,
                                "message": msg
                            }), 403
                        flash(msg, "error")
                        return render_template("login.html")

                    session["id_usuario"] = id_user_db
                    session["usuario"] = user_db
                    session["nombre"] = nombre_db
                    session["rol"] = rol_db

                    if rol_db == "ADMIN":
                        destino = url_for("admin_view")
                    elif rol_db in ["BACKOFFICE", "BACK", "BACK_OFFICE"]:
                        destino = url_for("backoffice_view")
                    elif rol_db == "POSTVENTA":
                        destino = url_for("postventa_view")
                    else:
                        destino = url_for("campo_view")

                    if es_ajax or request.data:
                        return jsonify({
                            "ok": True,
                            "success": True,
                            "status": "success",
                            "rol": rol_db,
                            "role": rol_db.lower(),
                            "nombre": nombre_db,
                            "usuario": user_db,
                            "redirect": destino,
                            "redirect_url": destino,
                            "url": destino
                        })
                    return redirect(destino)

            msg_err = "Usuario o contraseña incorrectos."
            if es_ajax or request.data:
                return jsonify({
                    "ok": False,
                    "success": False,
                    "status": "error",
                    "error": msg_err,
                    "msg": msg_err,
                    "message": msg_err
                }), 401
            flash(msg_err, "error")
        except Exception as e:
            msg_ex = f"Error al conectar con Google Sheets: {str(e)}"
            if es_ajax or request.data:
                return jsonify({
                    "ok": False,
                    "success": False,
                    "status": "error",
                    "error": msg_ex,
                    "msg": msg_ex,
                    "message": msg_ex
                }), 500
            flash(msg_ex, "error")

    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/campo")
@login_required
def campo_view():
    usuario = session.get("usuario")
    nombre = session.get("nombre", usuario)
    rol = session.get("rol", "VENTAS")
    return render_template("campo.html", usuario=usuario, nombre=nombre, rol=rol)

@app.route("/backoffice")
@login_required
def backoffice_view():
    return render_template("backoffice.html", usuario=session.get("usuario"), nombre=session.get("nombre"), rol=session.get("rol", "BACKOFFICE"))

@app.route("/admin")
@login_required
def admin_view():
    if session.get("rol") != "ADMIN":
        return redirect(url_for("backoffice_view"))
    return render_template("admin.html", usuario=session.get("usuario"), nombre=session.get("nombre"), rol="ADMIN")

@app.route("/postventa")
@login_required
def postventa_view():
    return render_template("postventa.html", usuario=session.get("usuario"), nombre=session.get("nombre"), rol=session.get("rol"))

# ==========================================================
# FUNCIÓN AUXILIAR: ENVIAR VENTA DIRECTO A BACKOFFICE
# ==========================================================
def registrar_venta_en_bandeja_back(sh, asesor, dni_ruc, cliente, celular, distrito, direccion, coordenadas, plan, observaciones, origen_base_id="", correo=""):
    ws_ventas = get_or_create_ventas_sheet(sh)
    filas_actuales = len(ws_ventas.get_all_values())
    id_venta = f"V{1000 + filas_actuales}"
    ahora_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    nueva_fila = [
        id_venta,                   # A: ID_VENTA
        ahora_str,                  # B: FECHA
        asesor,                     # C: ASESOR
        dni_ruc,                    # D: DNI_RUC
        cliente,                    # E: CLIENTE
        celular,                    # F: CELULAR
        distrito,                   # G: DISTRITO
        direccion,                  # H: DIRECCION
        coordenadas,                # I: COORDENADAS
        plan,                       # J: PLAN
        observaciones,              # K: OBSERVACIONES
        "PENDIENTE VALIDACIÓN",     # L: ESTADO
        "",                         # M: COMENTARIO_BACK
        origen_base_id,             # N: ORIGEN_BASE_ID
        correo,                     # O: CORREO
        "",                         # P: NUMERO_RECIBO_CLIENTE
        "",                         # Q: FECHA_VENCIMIENTO_RECIBO
        "Pendiente",                # R: ESTADO_PAGO_CLIENTE
        "Pendiente instalación",    # S: ESTADO_COMISION
        ""                          # T: FECHA_PAGO_COMISION
    ]
    ws_ventas.append_row(nueva_fila, value_input_option="USER_ENTERED")
    return id_venta

@app.route("/api/campo/registrar_venta", methods=["POST"])
@login_required
def api_registrar_venta():
    try:
        data = request.get_json() if request.is_json else request.form.to_dict()
        sh = get_spreadsheet()
        asesor = session.get("nombre") or session.get("usuario")

        id_v = registrar_venta_en_bandeja_back(
            sh=sh,
            asesor=asesor,
            dni_ruc=data.get("dni_ruc", ""),
            cliente=data.get("cliente", ""),
            celular=data.get("celular", ""),
            distrito=data.get("distrito", ""),
            direccion=data.get("direccion", ""),
            coordenadas=data.get("coordenadas", ""),
            plan=data.get("plan", ""),
            observaciones=data.get("observaciones", ""),
            origen_base_id=data.get("origen_base_id", "EXTERNA"),
            correo=data.get("correo", "").strip()
        )
        return jsonify({"ok": True, "msg": f"Venta {id_v} enviada a la bandeja de Back Office."})
    except Exception as e:
        return jsonify({"ok": False, "msg": f"Error al registrar venta: {str(e)}"}), 500

# ==========================================================
# API CAMPO: GESTIÓN DE HOJA 'BASE DE DATOS' Y MIS VENTAS
# ==========================================================
@app.route("/api/campo/mi_base", methods=["GET"])
@login_required
def api_campo_mi_base():
    try:
        usuario = session.get("usuario")
        nombre = session.get("nombre", usuario)
        rol = session.get("rol", "VENTAS")
        identificadores = {usuario.lower(), nombre.lower()}

        sh = get_spreadsheet()
        ws = get_or_create_base_sheet(sh)
        registros = ws.get_all_records()

        asignado_actual = None
        mis_cuentas = []
        usados_hoy = 0

        for idx, r in enumerate(registros, start=2):
            r["_fila"] = idx
            estado = str(r.get("ESTADO", "")).strip().upper()
            asig = str(r.get("ASIGNADO_A", "")).strip()
            ult_u = str(r.get("ULT_USUARIO", "")).strip()

            if asig.lower() in identificadores:
                usados_hoy += 1
                if estado == "ASIGNADO" and not asignado_actual:
                    asignado_actual = r
                elif estado in ["VENDIDO", "EN GESTIÓN", "AGENDADO"]:
                    mis_cuentas.append(r)
            elif ult_u.lower() in identificadores:
                usados_hoy += 1

        mis_ventas = []
        try:
            ws_ventas = get_or_create_ventas_sheet(sh)
            for v in reversed(ws_ventas.get_all_records()):
                asesor_v = str(v.get("ASESOR") or v.get("Asesor") or "").strip().lower()
                if rol == "ADMIN" or asesor_v in identificadores:
                    mis_ventas.append(v)
        except Exception:
            pass

        return jsonify({
            "ok": True,
            "usuario": nombre,
            "asignado": asignado_actual,
            "mis_cuentas": mis_cuentas,
            "mis_ventas": mis_ventas,
            "usados": usados_hoy,
            "cupo_max": CFG_BASE["cupo"]
        })
    except Exception as e:
        return jsonify({"ok": False, "msg": f"Error al leer BASE DE DATOS: {str(e)}"}), 500

@app.route("/api/campo/solicitar_registro", methods=["POST"])
@login_required
def api_campo_solicitar_registro():
    try:
        usuario = session.get("usuario")
        nombre = session.get("nombre", usuario)
        identificadores = {usuario.lower(), nombre.lower()}

        sh = get_spreadsheet()
        ws = get_or_create_base_sheet(sh)
        registros = ws.get_all_records()
        hoy_str = datetime.now().strftime("%Y-%m-%d")

        usados = 0
        for idx, r in enumerate(registros, start=2):
            estado = str(r.get("ESTADO", "")).strip().upper()
            asig = str(r.get("ASIGNADO_A", "")).strip()
            ult_u = str(r.get("ULT_USUARIO", "")).strip()
            if asig.lower() in identificadores or ult_u.lower() in identificadores:
                usados += 1
            if asig.lower() in identificadores and estado == "ASIGNADO":
                r["_fila"] = idx
                return jsonify({
                    "ok": False,
                    "msg": "Primero tipifica el registro que tienes asignado.",
                    "registro": r
                }), 400

        if usados >= CFG_BASE["cupo"]:
            return jsonify({"ok": False, "msg": f"Llegaste a tu cupo de {CFG_BASE['cupo']} registros."}), 400

        pool = []
        for idx, r in enumerate(registros, start=2):
            tiene_datos = any([r.get("RUC"), r.get("DNI"), r.get("RAZON_SOCIAL"), r.get("NOMBRE"), r.get("CELULAR")])
            if not tiene_datos:
                continue

            estado = str(r.get("ESTADO", "")).strip().upper()
            if estado == "":
                estado = "LIBRE"

            ult_user = str(r.get("ULT_USUARIO", "")).strip().lower()
            disp = str(r.get("DISPONIBLE_DESDE", "")).strip()

            if estado == "LIBRE" and ult_user not in identificadores:
                if not disp or disp <= hoy_str:
                    r["_fila"] = idx
                    if not r.get("ID"):
                        r["ID"] = f"B{1000 + idx - 1}"
                    pool.append(r)

        if not pool:
            return jsonify({"ok": False, "msg": "No hay registros libres disponibles en BASE DE DATOS."}), 404

        elegido = random.choice(pool)
        fila = elegido["_fila"]

        if not ws.cell(fila, 1).value:
            ws.update_cell(fila, 1, elegido["ID"])

        ws.update(f"I{fila}:J{fila}", [["ASIGNADO", nombre]])
        elegido["ESTADO"] = "ASIGNADO"
        elegido["ASIGNADO_A"] = nombre

        return jsonify({"ok": True, "registro": elegido})
    except Exception as e:
        return jsonify({"ok": False, "msg": f"Error al solicitar registro: {str(e)}"}), 500

@app.route("/api/campo/tipificar", methods=["POST"])
@login_required
def api_campo_tipificar():
    try:
        data = request.get_json() or {}
        usuario = session.get("usuario")
        nombre = session.get("nombre", usuario)

        id_reg = str(data.get("id", "")).strip()
        fila_param = data.get("fila")
        sub = str(data.get("tipificacion", "")).strip()
        plan_elegido = str(data.get("plan_elegido") or sub).strip()
        obs = str(data.get("observaciones", "")).strip()
        fecha_agenda = str(data.get("fecha_agenda", "")).strip()
        direccion_venta = str(data.get("direccion", "")).strip()
        correo_venta = str(data.get("correo", "")).strip()

        if not sub:
            return jsonify({"ok": False, "msg": "Elige la tipificación antes de guardar."}), 400

        sh = get_spreadsheet()
        ws = get_or_create_base_sheet(sh)
        registros = ws.get_all_records()

        fila_encontrada = None
        rec = None

        for idx, r in enumerate(registros, start=2):
            if (id_reg and str(r.get("ID", "")).strip() == id_reg) or (fila_param and idx == int(fila_param)):
                fila_encontrada = idx
                rec = r
                break

        if not rec:
            return jsonify({"ok": False, "msg": "No se encontró el registro en BASE DE DATOS."}), 404

        ahora = datetime.now()
        try:
            intentos = int(rec.get("INTENTOS") or 0)
        except ValueError:
            intentos = 0

        nuevo_estado = str(rec.get("ESTADO", "LIBRE")).strip().upper()
        asignado_a = nombre
        ult_usuario = nombre
        vence = ""
        disponible = ""
        agenda = ""
        motivo = f"[Correo: {correo_venta}] {obs}".strip() if correo_venta else obs
        id_venta_creada = None

        def soltar_a_base():
            nonlocal nuevo_estado, asignado_a, ult_usuario, vence, disponible
            nuevo_estado = "LIBRE"
            ult_usuario = nombre
            asignado_a = ""
            vence = ""
            disponible = (ahora + timedelta(days=CFG_BASE["diasRetorno"])).strftime("%Y-%m-%d")

        if sub in ["Venta Móvil", "Venta Fija", "Venta Móvil y Fija"] or sub.startswith("Venta"):
            nuevo_estado = "VENDIDO"
            dni_o_ruc = str(rec.get("RUC") or rec.get("DNI") or "").strip()
            nom_cliente = str(rec.get("RAZON_SOCIAL") if rec.get("RAZON_SOCIAL") not in ["", "—"] else rec.get("NOMBRE")).strip()
            id_venta_creada = registrar_venta_en_bandeja_back(
                sh=sh,
                asesor=nombre,
                dni_ruc=dni_o_ruc,
                cliente=nom_cliente,
                celular=str(rec.get("CELULAR", "")),
                distrito=str(rec.get("DISTRITO", "")),
                direccion=direccion_venta,
                coordenadas="",
                plan=plan_elegido,
                observaciones=obs,
                origen_base_id=str(rec.get("ID") or f"Fila-{fila_encontrada}"),
                correo=correo_venta
            )
        elif sub in ["Interesado en propuesta", "Se envía propuesta"]:
            nuevo_estado = "EN GESTIÓN"
            vence = (ahora + timedelta(days=CFG_BASE["diasInteres"])).strftime("%Y-%m-%d")
        elif sub == "Cl indica llamar nuevamente":
            nuevo_estado = "AGENDADO"
            agenda = fecha_agenda
            vence = (ahora + timedelta(days=CFG_BASE["diasAgenda"])).strftime("%Y-%m-%d")
        elif sub == "No contesta":
            intentos += 1
            if intentos >= CFG_BASE["maxNoContesta"]:
                nuevo_estado, asignado_a, motivo = "EXCLUIDO", "", f"Máx. intentos ({obs})".strip()
            else:
                soltar_a_base()
        elif sub == "Corta llamada":
            intentos += 1
            if intentos >= CFG_BASE["maxCorta"]:
                nuevo_estado, asignado_a, motivo = "EXCLUIDO", "", f"Corta llamada x2 ({obs})".strip()
            else:
                soltar_a_base()
        elif sub == "Sin contacto":
            intentos += 1
            if intentos >= CFG_BASE["maxSinContacto"]:
                nuevo_estado, asignado_a, motivo = "EXCLUIDO", "", f"Número inválido ({obs})".strip()
            else:
                soltar_a_base()
        elif sub == "No desea":
            nuevo_estado, asignado_a, motivo = "EXCLUIDO", "", f"No desea ({obs})".strip()
        elif sub == "Cliente crítico":
            nuevo_estado, asignado_a, motivo = "BLOQUEADO", "", f"Cliente crítico ({obs})".strip()

        valores_actualizados = [[
            nuevo_estado,   # I: ESTADO
            asignado_a,     # J: ASIGNADO_A
            ult_usuario,    # K: ULT_USUARIO
            intentos,       # L: INTENTOS
            plan_elegido,   # M: ULT_TIPIFICACION
            agenda,         # N: FECHA_AGENDA
            vence,          # O: FECHA_VENCE
            disponible,     # P: DISPONIBLE_DESDE
            motivo          # Q: MOTIVO_OBSERVACION
        ]]
        ws.update(f"I{fila_encontrada}:Q{fila_encontrada}", valores_actualizados)

        mensaje_ok = f"Guardado: {plan_elegido}"
        if id_venta_creada:
            mensaje_ok = f"¡Venta registrada! Enviada directo a Back Office ({id_venta_creada})."

        return jsonify({
            "ok": True,
            "msg": mensaje_ok,
            "nuevo_estado": nuevo_estado,
            "id_venta": id_venta_creada
        })
    except Exception as e:
        return jsonify({"ok": False, "msg": f"Error al guardar tipificación: {str(e)}"}), 500

# ==========================================================
# API BACKOFFICE Y ADMIN
# ==========================================================
@app.route("/api/backoffice/datos", methods=["GET"])
@login_required
def api_backoffice_datos():
    try:
        sh = get_spreadsheet()
        ws_base = get_or_create_base_sheet(sh)
        ws_ventas = get_or_create_ventas_sheet(sh)
        ws_usuarios = get_or_create_usuarios_sheet(sh)

        raw_usuarios = ws_usuarios.get_all_records()
        usuarios_list = []
        ejecutivos_stats = {}

        for idx, u in enumerate(raw_usuarios, start=2):
            u["_fila"] = idx
            nombre_u = str(u.get("NOMBRE_COMPLETO") or u.get("USUARIO") or "").strip()
            user_u = str(u.get("USUARIO") or "").strip()
            rol_u = str(u.get("ROL") or "VENTAS").strip().upper()
            estado_u = str(u.get("ESTADO") or "Activo").strip()
            usuarios_list.append(u)

            if rol_u in ["VENTAS", "CAMPO", "ASESOR"] and nombre_u:
                ejecutivos_stats[nombre_u.upper()] = {
                    "nombre": nombre_u,
                    "usuario": user_u,
                    "estado": estado_u,
                    "fila_usuario": idx,
                    "gestionados_total": 0,
                    "asignados_ahora": 0,
                    "en_gestion": 0,
                    "agendados": 0,
                    "no_efectivos": 0,
                    "ventas_base": 0,
                    "ventas_totales": 0
                }

        raw_base = ws_base.get_all_records()
        base_list = []
        for idx, r in enumerate(raw_base, start=2):
            if not any([r.get("RUC"), r.get("DNI"), r.get("RAZON_SOCIAL"), r.get("NOMBRE"), r.get("CELULAR")]):
                continue
            r["_fila"] = idx
            if not r.get("ID"):
                r["ID"] = f"B{1000 + idx - 1}"
            if not r.get("ESTADO"):
                r["ESTADO"] = "LIBRE"
            base_list.append(r)

            st = str(r.get("ESTADO", "LIBRE")).strip().upper()
            asig = str(r.get("ASIGNADO_A", "")).strip().upper()
            ult = str(r.get("ULT_USUARIO", "")).strip().upper()
            responsable = asig or ult

            if responsable:
                if responsable not in ejecutivos_stats:
                    ejecutivos_stats[responsable] = {
                        "nombre": r.get("ASIGNADO_A") or r.get("ULT_USUARIO"),
                        "usuario": responsable.lower(),
                        "estado": "Activo",
                        "fila_usuario": None,
                        "gestionados_total": 0,
                        "asignados_ahora": 0,
                        "en_gestion": 0,
                        "agendados": 0,
                        "no_efectivos": 0,
                        "ventas_base": 0,
                        "ventas_totales": 0
                    }
                ek = ejecutivos_stats[responsable]
                ek["gestionados_total"] += 1
                if st == "ASIGNADO":
                    ek["asignados_ahora"] += 1
                elif st == "EN GESTIÓN":
                    ek["en_gestion"] += 1
                elif st == "AGENDADO":
                    ek["agendados"] += 1
                elif st == "VENDIDO":
                    ek["ventas_base"] += 1
                elif st in ["LIBRE", "EXCLUIDO", "BLOQUEADO"]:
                    ek["no_efectivos"] += 1

        raw_ventas = ws_ventas.get_all_records()
        ventas_list = []
        for idx, v in enumerate(raw_ventas, start=2):
            v["_fila"] = idx
            ventas_list.append(v)
            asesor_v = str(v.get("ASESOR") or "").strip().upper()
            if asesor_v in ejecutivos_stats:
                ejecutivos_stats[asesor_v]["ventas_totales"] += 1

        ventas_list.reverse()

        return jsonify({
            "ok": True,
            "base": base_list,
            "ventas": ventas_list,
            "ejecutivos": list(ejecutivos_stats.values()),
            "usuarios": usuarios_list,
            "cupo_max": CFG_BASE["cupo"]
        })
    except Exception as e:
        return jsonify({"ok": False, "msg": f"Error cargando datos: {str(e)}"}), 500

@app.route("/api/backoffice/actualizar_venta", methods=["POST"])
@login_required
def api_backoffice_actualizar_venta():
    try:
        data = request.get_json() or {}
        fila = int(data.get("fila", 0))
        nuevo_estado = str(data.get("estado", "")).strip()
        comentario_back = str(data.get("comentario_back", "")).strip()
        origen_base_id = str(data.get("origen_base_id", "")).strip()

        if fila < 2 or not nuevo_estado:
            return jsonify({"ok": False, "msg": "Datos inválidos para actualizar la venta."}), 400

        sh = get_spreadsheet()
        ws_ventas = get_or_create_ventas_sheet(sh)
        ws_ventas.update(f"L{fila}:M{fila}", [[nuevo_estado, comentario_back]])

        if origen_base_id and origen_base_id not in ["MANUAL", "EXTERNA"]:
            ws_base = get_or_create_base_sheet(sh)
            registros_base = ws_base.get_all_records()
            for idx, r in enumerate(registros_base, start=2):
                if str(r.get("ID", "")).strip() == origen_base_id:
                    obs_actual = str(r.get("MOTIVO_OBSERVACION", "")).strip()
                    nueva_obs = f"[Back: {nuevo_estado}] {comentario_back} | {obs_actual}".strip(" |")
                    ws_base.update_cell(idx, 17, nueva_obs)
                    break

        return jsonify({"ok": True, "msg": f"Estado de venta actualizado a: {nuevo_estado}"})
    except Exception as e:
        return jsonify({"ok": False, "msg": f"Error al actualizar venta: {str(e)}"}), 500

@app.route("/api/backoffice/actualizar_base", methods=["POST"])
@login_required
def api_backoffice_actualizar_base():
    try:
        data = request.get_json() or {}
        fila = int(data.get("fila", 0))
        nuevo_estado = str(data.get("estado", "")).strip().upper()
        asignado_a = str(data.get("asignado_a", "")).strip()

        if fila < 2 or not nuevo_estado:
            return jsonify({"ok": False, "msg": "Fila o estado inválido."}), 400

        if nuevo_estado == "LIBRE":
            asignado_a = ""

        sh = get_spreadsheet()
        ws_base = get_or_create_base_sheet(sh)
        ws_base.update(f"I{fila}:J{fila}", [[nuevo_estado, asignado_a]])

        return jsonify({"ok": True, "msg": f"Registro de base actualizado a {nuevo_estado}."})
    except Exception as e:
        return jsonify({"ok": False, "msg": f"Error al actualizar BASE DE DATOS: {str(e)}"}), 500

# ==========================================================
# API POST-VENTA (/api/ventas)
# ==========================================================
@app.route("/api/ventas", methods=["GET"])
@login_required
def api_get_ventas_postventa():
    try:
        sh = get_spreadsheet()
        ws_ventas = get_or_create_ventas_sheet(sh)
        raw_ventas = ws_ventas.get_all_records()
        data_out = []
        for idx, v in enumerate(raw_ventas, start=2):
            plan_str = str(v.get("PLAN", ""))
            monto_com = 69 if "600" in plan_str else 59
            est_bo = str(v.get("ESTADO", "PENDIENTE VALIDACIÓN"))
            data_out.append({
                "_fila": idx,
                "ID_VENTA": v.get("ID_VENTA", f"V{1000+idx-1}"),
                "CLIENTE_NOMBRE": v.get("CLIENTE", ""),
                "CORREO": v.get("CORREO", ""),
                "ASESOR_CAMPO": v.get("ASESOR", ""),
                "PLAN_PRODUCTO": plan_str,
                "ESTADO_INSTALACION": "Instalado" if ("INSTALADO" in est_bo.upper() or "ACTIVADO" in est_bo.upper()) else est_bo,
                "NUMERO_RECIBO_CLIENTE": v.get("NUMERO_RECIBO_CLIENTE", ""),
                "FECHA_VENCIMIENTO_RECIBO": v.get("FECHA_VENCIMIENTO_RECIBO", ""),
                "ESTADO_PAGO_CLIENTE": v.get("ESTADO_PAGO_CLIENTE") or "Pendiente",
                "ESTADO_COMISION": v.get("ESTADO_COMISION") or "Pendiente instalación",
                "FECHA_PAGO_COMISION": v.get("FECHA_PAGO_COMISION", ""),
                "MONTO_COMISION": monto_com
            })
        return jsonify({"status": "success", "data": data_out})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/ventas/<id_venta>", methods=["PATCH"])
@login_required
def api_patch_venta_postventa(id_venta):
    try:
        payload = request.get_json() or {}
        sh = get_spreadsheet()
        ws_ventas = get_or_create_ventas_sheet(sh)
        registros = ws_ventas.get_all_records()
        fila_encontrada = None
        for idx, r in enumerate(registros, start=2):
            if str(r.get("ID_VENTA", "")).strip() == str(id_venta).strip():
                fila_encontrada = idx
                break
        if not fila_encontrada:
            return jsonify({"status": "error", "message": "Venta no encontrada"}), 404

        valores_pv = [[
            str(payload.get("numero_recibo", "")).strip(),
            str(payload.get("fecha_vencimiento_recibo", "")).strip(),
            str(payload.get("estado_pago_cliente", "Pendiente")).strip(),
            str(payload.get("estado_comision", "Pendiente instalación")).strip(),
            str(payload.get("fecha_pago_comision", "")).strip()
        ]]
        ws_ventas.update(f"P{fila_encontrada}:T{fila_encontrada}", valores_pv)
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# ==========================================================
# API EXCLUSIVA DE ADMIN: CREAR Y GESTIONAR USUARIOS
# ==========================================================
@app.route("/api/admin/crear_usuario", methods=["POST"])
@login_required
def api_admin_crear_usuario():
    if session.get("rol") != "ADMIN":
        return jsonify({"ok": False, "msg": "No autorizado. Solo ADMIN puede crear usuarios."}), 403

    try:
        data = request.get_json() or {}
        nombre_completo = str(data.get("nombre_completo", "")).strip().upper()
        usuario_login = str(data.get("usuario", "")).strip()
        password_login = str(data.get("password", "")).strip()
        rol_nuevo = str(data.get("rol", "VENTAS")).strip().upper()
        estado_nuevo = str(data.get("estado", "Activo")).strip()

        if not nombre_completo or not usuario_login or not password_login:
            return jsonify({"ok": False, "msg": "Completa Nombre Completo, Usuario y Password."}), 400

        sh = get_spreadsheet()
        ws_usuarios = get_or_create_usuarios_sheet(sh)
        existentes = ws_usuarios.get_all_records()

        for u in existentes:
            if str(u.get("USUARIO", "")).strip().lower() == usuario_login.lower():
                return jsonify({"ok": False, "msg": f"El usuario '{usuario_login}' ya existe."}), 400

        nuevo_num = len(existentes) + 1
        id_usuario = f"U-{nuevo_num:03d}"

        nueva_fila = [id_usuario, nombre_completo, usuario_login, password_login, rol_nuevo, estado_nuevo]
        ws_usuarios.append_row(nueva_fila, value_input_option="USER_ENTERED")

        return jsonify({
            "ok": True,
            "msg": f"Usuario {nombre_completo} ({id_usuario}) creado exitosamente en la hoja Usuarios."
        })
    except Exception as e:
        return jsonify({"ok": False, "msg": f"Error al crear usuario: {str(e)}"}), 500

@app.route("/api/admin/actualizar_usuario", methods=["POST"])
@login_required
def api_admin_actualizar_usuario():
    if session.get("rol") != "ADMIN":
        return jsonify({"ok": False, "msg": "Solo ADMIN puede modificar usuarios."}), 403

    try:
        data = request.get_json() or {}
        fila = int(data.get("fila", 0))
        password_nuevo = str(data.get("password", "")).strip()
        rol_nuevo = str(data.get("rol", "VENTAS")).strip().upper()
        estado_nuevo = str(data.get("estado", "Activo")).strip()

        if fila < 2:
            return jsonify({"ok": False, "msg": "Fila de usuario inválida."}), 400

        sh = get_spreadsheet()
        ws_usuarios = get_or_create_usuarios_sheet(sh)
        ws_usuarios.update(f"D{fila}:F{fila}", [[password_nuevo, rol_nuevo, estado_nuevo]])

        return jsonify({"ok": True, "msg": "Usuario actualizado correctamente."})
    except Exception as e:
        return jsonify({"ok": False, "msg": f"Error al actualizar usuario: {str(e)}"}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)