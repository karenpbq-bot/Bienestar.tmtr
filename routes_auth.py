from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from models import db, UsuarioUni, PacienteUni, EspecialistaUni, ClienteEmpresa
from functools import wraps

auth_bp = Blueprint('auth', __name__)

# ===========================================================================
# DECORADORES DE SEGURIDAD Y ROLES (RBAC)
# ===========================================================================

def login_required(f):
    """Verifica que el usuario haya iniciado sesión"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Por favor inicie sesión para acceder al sistema.', 'warning')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function

def role_required(*roles):
    """Verifica que el usuario tenga uno de los roles permitidos"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                flash('Por favor inicie sesión para continuar.', 'warning')
                return redirect(url_for('auth.login'))
            
            user_role = session.get('user_role')
            if user_role not in roles:
                flash('No cuenta con los permisos necesarios para acceder a esta sección.', 'danger')
                return redirect(url_for('dashboard'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator


# ===========================================================================
# FUNCIÓN UNIVERSAL PARA CARGAR DATOS Y LOGO DE LA EMPRESA EN LA SESIÓN
# ===========================================================================

def preparar_sesion_usuario(usuario_o_entidad, rol_asignado, id_cliente):
    """
    Función genérica y escalable: registra los datos clave del usuario y 
    busca automáticamente el logotipo de la empresa para cualquier rol actual o futuro.
    """
    session['user_role'] = rol_asignado
    session['id_cliente'] = id_cliente
    
    # Búsqueda universal del logo y datos de la empresa cliente
    if id_cliente:
        cliente = ClienteEmpresa.query.get(id_cliente)
        if cliente and cliente.nombre_marca:
            session['codigo_empresa'] = cliente.codigo_invitacion_5d
            session['nombre_marca_cliente'] = cliente.nombre_marca
            # Limpiamos el nombre para que coincida exactamente con el archivo .png (minúsculas y sin espacios)
            session['codigo_empresa_logo'] = cliente.nombre_marca.lower().replace(" ", "")
        else:
            session.pop('codigo_empresa', None)
            session.pop('nombre_marca_cliente', None)
            session.pop('codigo_empresa_logo', None)
    else:
        # Si es un Superadmin global sin empresa asignada, limpiamos los rastros de marca blanca
        session.pop('codigo_empresa', None)
        session.pop('nombre_marca_cliente', None)
        session.pop('codigo_empresa_logo', None)


# ===========================================================================
# RUTAS DE AUTENTICACIÓN
# ===========================================================================

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Gestiona el inicio de sesión unificado para el ecosistema"""
    
    # -----------------------------------------------------------------------
    # GESTIÓN DEL MÉTODO GET: Cargar la pantalla y buscar el logo del cliente
    # -----------------------------------------------------------------------
    if request.method == 'GET':
        codigo_cliente = request.args.get('c')
        logo_cliente = None

        if codigo_cliente:
            cliente = ClienteEmpresa.query.filter_by(codigo_invitacion_5d=codigo_cliente).first()
            
            if cliente and cliente.nombre_marca:
                nombre_archivo = cliente.nombre_marca.lower().replace(" ", "")
                logo_cliente = url_for('static', filename=f'logos/{nombre_archivo}.png')

        return render_template('login.html', logo_cliente=logo_cliente)

    # -----------------------------------------------------------------------
    # GESTIÓN DEL MÉTODO POST: Validar credenciales de forma universal
    # -----------------------------------------------------------------------
    if request.method == 'POST':
        correo = request.form.get('correo', '').strip().lower()
        password = request.form.get('password', '')

        if not correo or not password:
            flash('Por favor ingrese su correo y contraseña.', 'warning')
            return redirect(url_for('auth.login', c=request.args.get('c')))

        # 1. Buscar en Usuarios Universales (Superadmin, Administrador, Director, Recepcionista, etc.)
        usuario = UsuarioUni.query.filter_by(correo=correo).first()
        if usuario and usuario.check_password(password):
            if not usuario.estado:
                flash('Su cuenta se encuentra suspendida. Contacte al administrador.', 'danger')
                return redirect(url_for('auth.login', c=request.args.get('c')))
            
            # Registrar datos básicos
            session['user_id'] = usuario.id_usuario
            session['user_name'] = usuario.nombres_apellidos
            
            # Carga universal de rol, ID de cliente y logo (aplica para recepcionistas y futuros roles)
            preparar_sesion_usuario(usuario, usuario.rol, usuario.id_cliente)
            
            flash(f'Bienvenido al sistema, {usuario.nombres_apellidos}', 'success')
            return redirect(url_for('dashboard'))

        # 2. Buscar en Especialistas (Rol Asistencial)
        especialista = EspecialistaUni.query.filter_by(email=correo).first()
        if especialista and especialista.check_password(password):
            if not especialista.estado:
                flash('Su cuenta de especialista se encuentra inactiva.', 'danger')
                return redirect(url_for('auth.login', c=request.args.get('c')))
            
            session['user_id'] = especialista.id_especialista
            session['user_name'] = f"{especialista.nombre} {especialista.apellido}"
            
            # Carga universal de rol y logo para especialistas
            preparar_sesion_usuario(especialista, 'Especialista', especialista.id_cliente)
            
            flash(f'Bienvenido especialista, {especialista.nombre}', 'success')
            return redirect(url_for('dashboard'))

        # 3. Buscar en Pacientes (Rol Cliente Final)
        paciente = PacienteUni.query.filter_by(email=correo).first()
        if paciente and paciente.check_password(password):
            session['user_id'] = paciente.id_paciente
            session['user_name'] = f"{paciente.nombre} {paciente.apellido}"
            session['codigo_7d'] = paciente.codigo_invitacion_7d
            
            # Carga universal de rol y logo para pacientes
            preparar_sesion_usuario(paciente, 'Paciente', paciente.id_cliente)
            
            flash(f'Bienvenido a su portal, {paciente.nombre}', 'success')
            return redirect(url_for('portal_paciente'))

        flash('Credenciales incorrectas. Verifique su correo y contraseña.', 'danger')
        return redirect(url_for('auth.login', c=request.args.get('c')))


@auth_bp.route('/logout')
def logout():
    """Cierra la sesión del usuario actual limpiando el almacenamiento temporal"""
    session.clear()
    flash('Has cerrado sesión correctamente.', 'info')
    return redirect(url_for('auth.login'))


# ===========================================================================
# CAMBIO DE CONTRASEÑA
# ===========================================================================

@auth_bp.route('/cambiar-password', methods=['GET', 'POST'])
@login_required
def cambiar_password():
    """Permite al usuario cambiar su contraseña temporal (DNI o generada) por una propia"""
    if request.method == 'POST':
        password_actual = request.form.get('password_actual', '')
        nueva_password = request.form.get('nueva_password', '')
        confirmar_password = request.form.get('confirmar_password', '')

        # Validar que ningún campo esté vacío
        if not password_actual or not nueva_password or not confirmar_password:
            flash('Por favor complete todos los campos.', 'warning')
            return redirect(url_for('auth.cambiar_password'))

        # Validar que las nuevas contraseñas coincidan exactamente
        if nueva_password != confirmar_password:
            flash('Las nuevas contraseñas no coinciden.', 'danger')
            return redirect(url_for('auth.cambiar_password'))

        # Validar que la nueva contraseña tenga una longitud mínima de 8 caracteres
        if len(nueva_password) < 8:
            flash('La nueva contraseña debe tener al menos 8 caracteres.', 'warning')
            return redirect(url_for('auth.cambiar_password'))

        user_id = session.get('user_id')
        user_role = session.get('user_role')
        usuario_obj = None

        # Identificar la tabla correcta según el rol en sesión
        if user_role == 'Paciente':
            usuario_obj = PacienteUni.query.get(user_id)
        elif user_role == 'Especialista':
            usuario_obj = EspecialistaUni.query.get(user_id)
        else:
            usuario_obj = UsuarioUni.query.get(user_id)

        if usuario_obj:
            # Validar contraseña actual (DNI inicial o la generada por el superadmin)
            check = usuario_obj.check_password(password_actual) if hasattr(usuario_obj, 'check_password') else False
            
            if check:
                usuario_obj.set_password(nueva_password)
                db.session.commit()
                flash('¡Contraseña actualizada exitosamente! Por seguridad, inicie sesión nuevamente.', 'success')
                session.clear()
                return redirect(url_for('auth.login'))
            else:
                flash('La contraseña actual es incorrecta.', 'danger')
        else:
            flash('Usuario no encontrado.', 'danger')

        return redirect(url_for('auth.cambiar_password'))

    return render_template('cambiar_password.html')
