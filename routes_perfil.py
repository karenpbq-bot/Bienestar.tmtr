from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from models import db, EspecialistaUni, UsuarioUni
from routes_auth import login_required

perfil_bp = Blueprint('perfil', __name__, template_folder='templates')

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
