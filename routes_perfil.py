from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from models import db, EspecialistaUni, UsuarioUni, PacienteUni
from routes_auth import login_required

perfil_bp = Blueprint('perfil', __name__, template_folder='templates')

# --- 1. MÓDULO DE PERFIL DEL ESPECIALISTA ---
@perfil_bp.route('/perfil', methods=['GET', 'POST'])
@login_required
def gestionar_perfil():
    """Permite al especialista visualizar y actualizar sus datos profesionales"""
    user_id = session.get('user_id')
    cliente_id = session.get('id_cliente')
    rol = session.get('user_role')

    # Solo los especialistas gestionan su perfil clínico profesional aquí
    if rol != 'Especialista':
        flash('El módulo de perfil profesional está reservado para especialistas.', 'warning')
        return redirect(url_for('dashboard'))

    # Buscamos el registro del especialista vinculado al usuario actual
    especialista = EspecialistaUni.query.filter_by(
        id_cliente=cliente_id, 
        id_usuario=user_id
    ).first()

    if not especialista:
        flash('Error crítico: No se encontró el perfil de especialista asociado a su cuenta.', 'danger')
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        try:
            # 2. Datos profesionales
            especialista.telefono = request.form.get('telefono', '').strip()
            especialista.matricula = request.form.get('matricula', '').strip()
            especialista.rne = request.form.get('rne', '').strip()  # <-- CAPTURAR RNE
            
            esp_input = request.form.get('especialidades', '').strip()
            if esp_input:
                especialista.especialidades = [e.strip() for e in esp_input.split(',')]
            else:
                especialista.especialidades = []

            db.session.commit()
            flash('¡Información de perfil actualizada con éxito!', 'success')
            return redirect(url_for('perfil.gestionar_perfil'))

        except Exception as e:
            db.session.rollback()
            flash(f'Error al actualizar el perfil: {str(e)}', 'danger')

    return render_template('perfil.html', especialista=especialista)


# --- 2. MÓDULO DE PERFIL DEL PACIENTE ---
@perfil_bp.route('/mi-perfil-paciente', methods=['GET', 'POST'])
@login_required
def perfil_paciente():
    """Permite al paciente visualizar y actualizar sus datos personales y clínicos básicos"""
    user_id = session.get('user_id')
    cliente_id = session.get('id_cliente')
    rol = session.get('user_role')

    if rol != 'Paciente':
        flash('Acceso restringido al portal de pacientes.', 'warning')
        return redirect(url_for('dashboard'))

    # Buscamos el registro del paciente vinculado
    paciente = PacienteUni.query.filter_by(
        id_cliente=cliente_id, 
        id_paciente=user_id
    ).first()

    if not paciente:
        paciente = PacienteUni.query.filter_by(email=session.get('user_correo')).first()

    if not paciente:
        flash('Error crítico: No se encontró su ficha de paciente asociada.', 'danger')
        return redirect(url_for('dashboard'))

    usuario_asociado = UsuarioUni.query.get(user_id)

    if request.method == 'POST':
        try:
            # 1. Datos personales
            nombres = request.form.get('nombre', '').strip()
            apellidos = request.form.get('apellido', '').strip()
            dni = request.form.get('dni', '').strip() or None

            paciente.nombre = nombres
            paciente.apellido = apellidos
            paciente.dni = dni

            if usuario_asociado:
                usuario_asociado.nombres_apellidos = f"{nombres} {apellidos}"
                usuario_asociado.dni = dni

            # 2. Datos de contacto y demográficos
            paciente.telefono = request.form.get('telefono', '').strip()
            paciente.direccion = request.form.get('direccion', '').strip()
            
            # 3. Datos clínicos básicos
            paciente.grupo_sangre = request.form.get('grupo_sangre', '').strip()
            paciente.obra_social = request.form.get('obra_social', '').strip()
            paciente.nro_afiliado = request.form.get('nro_afiliado', '').strip()
            paciente.alergias = request.form.get('alergias', '').strip()

            fecha_nac_str = request.form.get('fecha_nac', '').strip()
            if fecha_nac_str:
                paciente.fecha_nac = datetime.strptime(fecha_nac_str, '%Y-%m-%d').date()

            db.session.commit()
            flash('¡Tus datos personales y clínicos han sido actualizados con éxito!', 'success')
            return redirect(url_for('perfil.perfil_paciente'))

        except Exception as e:
            db.session.rollback()
            flash(f'Error al actualizar el perfil: {str(e)}', 'danger')

    return render_template('perfil_paciente.html', paciente=paciente, usuario=usuario_asociado)
