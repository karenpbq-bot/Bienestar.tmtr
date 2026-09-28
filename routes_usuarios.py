from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from models import db, UsuarioUni, ClienteEmpresa, Codigo7D, PacienteUni
from functools import wraps
import random
import string
from datetime import datetime

usuarios_bp = Blueprint('usuarios', __name__, template_folder='templates')

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
            if session.get('user_role') not in roles:
                flash('No cuenta con los permisos necesarios para acceder a esta función.', 'danger')
                return redirect(url_for('dashboard'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator


# ===========================================================================
# 1. GESTIÓN Y LISTADO DE USUARIOS (Acceso: Admin, Director, Recepción, Superadmin)
# ===========================================================================

@usuarios_bp.route('/usuarios', methods=['GET'])
@login_required
@role_required('Superadmin', 'Administrador', 'Director', 'Recepcionista')
def gestionar_usuarios():
    rol = session.get('user_role')
    cliente_id = session.get('id_cliente')
    
    busqueda = request.args.get('q', '').strip()
    filtro_rol = request.args.get('rol', '').strip()
    filtro_cliente = request.args.get('id_cliente', '').strip()

    if rol == 'Superadmin':
        query = UsuarioUni.query
        if filtro_cliente:
            query = query.filter_by(id_cliente=filtro_cliente)
    else:
        # Blindaje multi-tenant: Solo ve usuarios de su propia empresa cliente
        query = UsuarioUni.query.filter(
            UsuarioUni.id_cliente == cliente_id,
            UsuarioUni.rol != 'Superadmin'
        )

    if filtro_rol:
        query = query.filter_by(rol=filtro_rol)

    if busqueda:
        termino = f"%{busqueda}%"
        query = query.filter(
            (UsuarioUni.nombres_apellidos.ilike(termino)) | 
            (UsuarioUni.correo.ilike(termino)) | 
            (UsuarioUni.dni.ilike(termino))
        )

    usuarios = query.order_by(UsuarioUni.id_usuario.desc()).all()
    clientes = ClienteEmpresa.query.all() if rol == 'Superadmin' else []

    # Obtener la lista de códigos de 7 dígitos generados para esta empresa
    codigos_7d_lista = []
    if rol == 'Administrador':
        codigos_7d_lista = Codigo7D.query.filter_by(id_cliente=cliente_id).order_by(Codigo7D.id.desc()).all()
    elif rol == 'Superadmin':
        codigos_7d_lista = Codigo7D.query.order_by(Codigo7D.id.desc()).all()

    return render_template(
        'usuarios.html', 
        usuarios=usuarios, 
        clientes=clientes, 
        codigos_7d_lista=codigos_7d_lista,
        current_user_role=rol
    )


# ===========================================================================
# 2. CREACIÓN DE NUEVO USUARIO (Con sincronización para Pacientes y Especialistas)
# ===========================================================================

@usuarios_bp.route('/usuarios/nuevo', methods=['POST'])
@login_required
@role_required('Superadmin', 'Administrador', 'Director', 'Recepcionista')
def nuevo_usuario():
    rol_sesion = session.get('user_role')
    cliente_id_sesion = session.get('id_cliente')

    nombres = request.form.get('nombres_apellidos', '').strip()
    dni = request.form.get('dni', '').strip() or None
    correo = request.form.get('correo', '').strip().lower()
    password = request.form.get('password', '').strip()
    rol = request.form.get('rol', '').strip()
    codigo_7d_ingresado = request.form.get('codigo_7d', '').strip().upper()
    
    # REGLA DE SEGURIDAD 1: Nadie puede crear un Superadmin
    if rol == 'Superadmin':
        flash('⚠️ Error de seguridad: Está estrictamente prohibido registrar perfiles de Superadmin.', 'danger')
        return redirect(url_for('usuarios.gestionar_usuarios'))

    # REGLA DE SEGURIDAD 2: Solo el Superadmin puede crear Administradores
    if rol == 'Administrador' and rol_sesion != 'Superadmin':
        flash('⚠️ Error de seguridad: Solo el Superadmin puede registrar perfiles de Administrador.', 'danger')
        return redirect(url_for('usuarios.gestionar_usuarios'))

    if rol_sesion == 'Superadmin':
        id_cli = request.form.get('id_cliente')
        id_cliente = int(id_cli) if id_cli else None
    else:
        id_cliente = cliente_id_sesion

    if not nombres or not correo or not password or not rol or not codigo_7d_ingresado:
        flash('Todos los campos obligatorios, incluyendo el código de 7 dígitos, deben ser completados.', 'warning')
        return redirect(url_for('usuarios.gestionar_usuarios'))

    # Validación de correspondencia del Código de 7 Dígitos Institucional
    codigo_obj = Codigo7D.query.filter_by(codigo=codigo_7d_ingresado, id_cliente=id_cliente).first()
    
    if not codigo_obj:
        flash('El código de 7 dígitos ingresado no existe para esta empresa.', 'danger')
        return redirect(url_for('usuarios.gestionar_usuarios'))
    
    if codigo_obj.rol_destino != rol:
        flash(f'Este código de 7 dígitos está asignado para el rol "{codigo_obj.rol_destino}", no para "{rol}".', 'danger')
        return redirect(url_for('usuarios.gestionar_usuarios'))

    # Verificar si el correo ya existe en usuarios
    existe = UsuarioUni.query.filter_by(correo=correo).first()
    if existe:
        flash('El correo electrónico ya se encuentra registrado en el sistema.', 'danger')
        return redirect(url_for('usuarios.gestionar_usuarios'))

    # 1. Crear el usuario en la tabla general UsuarioUni
    nuevo = UsuarioUni(
        nombres_apellidos=nombres,
        dni=dni,
        correo=correo,
        rol=rol,
        id_cliente=id_cliente,
        codigo_7d=codigo_7d_ingresado,
        estado=True
    )
    if password:
        nuevo.set_password(password)
    else:
        nuevo.set_password('Temp2026*')

    db.session.add(nuevo)

    # 2. SINCRONIZACIÓN AUTOMÁTICA CON LAS TABLAS CLÍNICAS EN SUPABASE
    if rol == 'Paciente':
        from models import PacienteUni
        partes_nombre = nombres.split(' ', 1)
        nombre_p = partes_nombre[0]
        apellido_p = partes_nombre[1] if len(partes_nombre) > 1 else 'Sin Apellido'
        
        # Verificar si ya existe en uni_pacientes
        paciente_existente = PacienteUni.query.filter_by(email=correo).first()
        if not paciente_existente:
            nuevo_paciente = PacienteUni(
                id_cliente=id_cliente,
                nombre=nombre_p,
                apellido=apellido_p,
                email=correo,
                dni=dni if dni else f"DNI_{random.randint(100000,999999)}",
                codigo_invitacion_7d=codigo_7d_ingresado
            )
            nuevo_paciente.set_password(password if password else 'Temp2026*')
            db.session.add(nuevo_paciente)

    elif rol == 'Especialista':
        from models import EspecialistaUni
        partes_nombre = nombres.split(' ', 1)
        nombre_e = partes_nombre[0]
        apellido_e = partes_nombre[1] if len(partes_nombre) > 1 else 'Sin Apellido'
        
        # Verificar si ya existe en uni_especialistas
        especialista_existente = EspecialistaUni.query.filter_by(email=correo).first()
        if not especialista_existente:
            nuevo_especialista = EspecialistaUni(
                id_cliente=id_cliente,
                nombre=nombre_e,
                apellido=apellido_e,
                email=correo,
                telefono=None
            )
            nuevo_especialista.set_password(password if password else 'Temp2026*')
            db.session.add(nuevo_especialista)

    db.session.commit()
    
    flash(f'Usuario "{nombres}" ({rol}) registrado exitosamente y sincronizado en Supabase.', 'success')
    return redirect(url_for('usuarios.gestionar_usuarios'))


# ===========================================================================
# 3. GENERADOR DE CÓDIGOS DE 7 DÍGITOS (Exclusivo para el Administrador)
# ===========================================================================

@usuarios_bp.route('/usuarios/generar-codigo-7d', methods=['POST'])
@login_required
@role_required('Administrador')
def generar_codigo_7d():
    """Genera aleatoriamente una combinación de 7 caracteres alfanuméricos"""
    cliente_id = session.get('id_cliente')
    rol_destino = request.form.get('rol_destino', '').strip()

    if not rol_destino:
        flash('Debe especificar el rol de destino para el código.', 'warning')
        return redirect(url_for('usuarios.gestionar_usuarios'))

    while True:
        caracteres = string.ascii_uppercase + string.digits
        codigo_aleatorio = ''.join(random.choice(caracteres) for _ in range(7))
        existe = Codigo7D.query.filter_by(codigo=codigo_aleatorio).first()
        if not existe:
            break

    nuevo_codigo = Codigo7D(
        codigo=codigo_aleatorio,
        rol_destino=rol_destino,
        id_cliente=cliente_id,
        usado=False,
        fecha=datetime.now()
    )

    db.session.add(nuevo_codigo)
    db.session.commit()

    flash(f'Código de 7 dígitos generado con éxito: {codigo_aleatorio} (Destinado a: {rol_destino})', 'success')
    return redirect(url_for('usuarios.gestionar_usuarios'))


# ===========================================================================
# 4. EDICIÓN, RESTABLECIMIENTO Y ELIMINACIÓN DE USUARIOS
# ===========================================================================

@usuarios_bp.route('/usuarios/editar/<int:id_usuario>', methods=['POST'])
@login_required
@role_required('Superadmin', 'Administrador', 'Director', 'Recepcionista')
def editar_usuario(id_usuario):
    usuario = UsuarioUni.query.get_or_404(id_usuario)
    rol_sesion = session.get('user_role')

    if rol_sesion != 'Superadmin' and usuario.id_cliente != session.get('id_cliente'):
        flash('No cuenta con autorización para editar este usuario.', 'danger')
        return redirect(url_for('usuarios.gestionar_usuarios'))
    
    nuevo_rol = request.form.get('rol', '').strip()
    if nuevo_rol == 'Administrador' and usuario.rol != 'Administrador':
        flash('No se puede asignar el rol de Administrador desde este panel.', 'danger')
        return redirect(url_for('usuarios.gestionar_usuarios'))

    usuario.nombres_apellidos = request.form.get('nombres_apellidos', '').strip()
    usuario.dni = request.form.get('dni', '').strip() or None
    usuario.correo = request.form.get('correo', '').strip().lower()
    usuario.rol = nuevo_rol
    
    if rol_sesion == 'Superadmin':
        id_cli = request.form.get('id_cliente')
        usuario.id_cliente = int(id_cli) if id_cli else None

    db.session.commit()
    flash('Usuario actualizado correctamente.', 'success')
    return redirect(url_for('usuarios.gestionar_usuarios'))

@usuarios_bp.route('/usuarios/reset/<int:id_usuario>', methods=['POST'])
@login_required
@role_required('Superadmin', 'Administrador', 'Director', 'Recepcionista')
def reset_password(id_usuario):
    usuario = UsuarioUni.query.get_or_404(id_usuario)
    rol_sesion = session.get('user_role')

    if rol_sesion != 'Superadmin' and usuario.id_cliente != session.get('id_cliente'):
        flash('No cuenta con autorización para realizar esta acción.', 'danger')
        return redirect(url_for('usuarios.gestionar_usuarios'))

    # Generar contraseña temporal de 8 dígitos
    pass_temporal = ''.join(random.choices(string.digits, k=8))
    
    usuario.set_password(pass_temporal)
    db.session.commit()
    
    flash(f'Contraseña de {usuario.nombres_apellidos} restablecida temporalmente. Su clave es: {pass_temporal}', 'success')
    return redirect(url_for('usuarios.gestionar_usuarios'))

@usuarios_bp.route('/usuarios/eliminar/<int:id_usuario>', methods=['POST'])
@login_required
@role_required('Superadmin', 'Administrador', 'Director', 'Recepcionista')
def eliminar_usuario(id_usuario):
    usuario = UsuarioUni.query.get_or_404(id_usuario)
    rol_sesion = session.get('user_role')

    if rol_sesion != 'Superadmin' and usuario.id_cliente != session.get('id_cliente'):
        flash('No cuenta con autorización para eliminar este usuario.', 'danger')
        return redirect(url_for('usuarios.gestionar_usuarios'))

    if usuario.id_usuario == session.get('user_id'):
        flash('No puede eliminar su propia cuenta activa.', 'danger')
    else:
        db.session.delete(usuario)
        db.session.commit()
        flash('Usuario eliminado correctamente.', 'success')
        
    return redirect(url_for('usuarios.gestionar_usuarios'))


# ===========================================================================
# 5. PANEL SUPERADMIN: RESTABLECIMIENTO Y EXTRACCIÓN DE CLAVE TEMPORAL
# ===========================================================================

@usuarios_bp.route('/usuarios/superadmin-reset/<int:id_usuario>', methods=['POST'])
@login_required
@role_required('Superadmin')
def superadmin_reset_password(id_usuario):
    usuario = UsuarioUni.query.get_or_404(id_usuario)
    
    # Generar contraseña temporal de 8 dígitos
    nueva_clave = ''.join(random.choices(string.digits, k=8))
    
    usuario.set_password(nueva_clave)
    db.session.commit()
    
    flash(f'ÉXITO_CLAVE::{usuario.correo}::{nueva_clave}', 'temporal_generada')
    return redirect(url_for('usuarios.gestionar_usuarios'))
