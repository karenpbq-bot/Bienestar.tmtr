from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from models import db, PerfilPersonalizado, ClientePerfilAsignado, ClienteEmpresa, ModuloSistema # <-- Añade ModuloSistema aquí
from functools import wraps

perfiles_superadmin_bp = Blueprint('perfiles_superadmin', __name__, template_folder='templates')

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
                flash('No cuenta con los permisos necesarios.', 'danger')
                return redirect(url_for('dashboard'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

@perfiles_superadmin_bp.route('/superadmin/perfiles', methods=['GET', 'POST'])
@login_required
@role_required('Superadmin')
def gestionar_perfiles():
    if request.method == 'POST':
        nombre_perfil = request.form.get('nombre_perfil', '').strip()
        codigo_perfil = request.form.get('codigo_perfil', '').strip().lower().replace(" ", "_")
        descripcion = request.form.get('descripcion', '').strip()
        modulos_seleccionados = request.form.getlist('modulos')

        if not nombre_perfil or not codigo_perfil:
            flash('El nombre y el código del perfil son obligatorios.', 'warning')
        else:
            existente = PerfilPersonalizado.query.filter_by(codigo_perfil=codigo_perfil).first()
            if existente:
                flash('Ya existe un perfil con ese código en el sistema.', 'danger')
            else:
                nuevo_perfil = PerfilPersonalizado(
                    nombre_perfil=nombre_perfil,
                    codigo_perfil=codigo_perfil,
                    descripcion=descripcion,
                    modulos_asociados=modulos_seleccionados,
                    estado=True
                )
                db.session.add(nuevo_perfil)
                db.session.commit()
                flash(f'Perfil "{nombre_perfil}" creado exitosamente.', 'success')

        return redirect(url_for('perfiles_superadmin.gestionar_perfiles'))

    perfiles = PerfilPersonalizado.query.all()
    return render_template('superadmin_perfiles.html', perfiles=perfiles)
