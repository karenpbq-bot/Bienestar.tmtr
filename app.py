from functools import wraps
from datetime import datetime, date
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from config import Config
from models import (
    db, get_peru_time, ClienteEmpresa, UsuarioUni, EspecialistaUni, 
    PacienteUni, DisponibilidadUni, CitaUni, ReprogramacionUni, 
    HistoriaClinicaPsi, SeguimientoPsi
)
from routes_perfil import perfil_bp

# 1. ÚNICA CREACIÓN DE LA INSTANCIA DE APP
app = Flask(__name__)
app.config.from_object(Config)
app.register_blueprint(perfil_bp)
db.init_app(app)

# --- REGISTRO DE BLUEPRINTS (MÓDULOS MODULARES) ---
from routes_auth import auth_bp
from routes_clientes import clientes_bp
from routes_usuarios import usuarios_bp
from routes_agenda import agenda_bp
from routes_pacientes import pacientes_bp
from routes_clinica import clinica_bp

app.register_blueprint(auth_bp)
app.register_blueprint(clientes_bp)
app.register_blueprint(usuarios_bp)
app.register_blueprint(agenda_bp)
app.register_blueprint(pacientes_bp)
app.register_blueprint(clinica_bp)

# --- CREACIÓN AUTOMÁTICA DEL SUPERADMIN / ADMIN PRINCIPAL ---
with app.app_context():
    db.create_all()
    admin_email = "kbarrientosq.2604@gmail.com"
    admin_user = UsuarioUni.query.filter_by(correo=admin_email).first()
    
    if not admin_user:
        nuevo_admin = UsuarioUni(
            nombres_apellidos="Karen Paola Barrientos",
            correo=admin_email,
            rol="Superadmin",
            id_cliente=None # Superadmin global sin clínica fija inicial
        )
        nuevo_admin.set_password("admin123")
        db.session.add(nuevo_admin)
        db.session.commit()
        print("¡Cuenta Superadmin creada exitosamente en la BD activa!")
    else:
        admin_user.rol = "Superadmin"
        admin_user.set_password("admin123")
        db.session.commit()
        print("¡Cuenta Superadmin verificada y actualizada!")

# --- Decoradores de Seguridad y Autenticación Globales ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Por favor inicie sesión para acceder al sistema.', 'warning')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function

def role_required(*roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                flash('Sesión no iniciada.', 'danger')
                return redirect(url_for('auth.login'))
            if session.get('user_role') not in roles:
                flash('No cuenta con los permisos necesarios para acceder a esta función.', 'danger')
                return redirect(url_for('dashboard'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# --- Context Processor blindado para evitar errores 500 ---
@app.context_processor
def inject_globals():
    cliente_nombre = "Psicolapp / Tamtara"
    cliente_id = session.get('id_cliente')
    
    try:
        if cliente_id:
            from models import ClienteEmpresa
            cliente_obj = ClienteEmpresa.query.get(cliente_id)
            if cliente_obj:
                cliente_nombre = cliente_obj.nombre_marca
        elif session.get('user_role') == 'Superadmin':
            cliente_nombre = "TAMTARA (Superadmin)"
    except Exception as e:
        print(f"Error en context_processor: {e}")

    return {
        'current_user_name': session.get('user_name'),
        'current_user_role': session.get('user_role'),
        'current_user_id': session.get('user_id'),
        'current_cliente_id': cliente_id,
        'current_cliente_nombre': cliente_nombre
    }

# --- Dashboard Principal (Aislado por id_cliente) ---
@app.route('/')
@login_required
def dashboard():
    rol = session.get('user_role')
    cliente_id = session.get('id_cliente')

    # Filtrado multi-tenant según el rol y la empresa
    if rol == 'Superadmin':
        total_pacientes = PacienteUni.query.count()
        total_usuarios = UsuarioUni.query.count()
        total_especialistas = EspecialistaUni.query.count()
        citas = CitaUni.query.order_by(CitaUni.fecha_hora_inicio.asc()).all()
        total_historias = HistoriaClinicaPsi.query.count()
    else:
        total_pacientes = PacienteUni.query.filter_by(id_cliente=cliente_id).count()
        total_usuarios = UsuarioUni.query.filter_by(id_cliente=cliente_id).count()
        total_especialistas = EspecialistaUni.query.filter_by(id_cliente=cliente_id).count()
        citas = CitaUni.query.filter_by(id_cliente=cliente_id).order_by(CitaUni.fecha_hora_inicio.asc()).all()
        
        total_historias = HistoriaClinicaPsi.query.join(PacienteUni).filter(PacienteUni.id_cliente == cliente_id).count()

    citas_programadas = sum(1 for c in citas if c.estado_cita == 'Programada')
    citas_completadas = sum(1 for c in citas if c.estado_cita == 'Completada')

    return render_template(
        'dashboard.html',
        citas=citas[:10],
        citas_programadas=citas_programadas,
        citas_completadas=citas_completadas,
        total_pacientes=total_pacientes,
        total_especialistas=total_especialistas,
        total_historias=total_historias,
        total_usuarios=total_usuarios
    )

# --- Ruta exclusiva para el Portal del Paciente ---
@app.route('/portal-paciente')
@login_required
@role_required('Paciente')
def portal_paciente():
    paciente_id = session.get('user_id')
    paciente = PacienteUni.query.get_or_404(paciente_id)
    citas_paciente = CitaUni.query.filter_by(id_paciente=paciente_id).order_by(CitaUni.fecha_hora_inicio.desc()).all()
    return render_template('portal_paciente.html', paciente=paciente, citas=citas_paciente)

if __name__ == '__main__':
    app.run(debug=True, port=5000)
