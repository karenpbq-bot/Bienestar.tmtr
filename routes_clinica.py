from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from models import db, get_peru_time, HistoriaClinicaPsi, SeguimientoPsi, PacienteUni, CitaUni
from routes_auth import login_required, role_required
from datetime import datetime

clinica_bp = Blueprint('clinica', __name__)

@clinica_bp.route('/historias')
@login_required
@role_required('Superadmin', 'Director', 'Administrador', 'Especialista', 'Recepcionista')
def listar_historias():
    """Lista las historias clínicas filtrando según el rol del usuario"""
    cliente_id = session.get('id_cliente')
    rol = session.get('user_role')
    user_id = session.get('user_id')

    if rol == 'Superadmin':
        lista_historias = HistoriaClinicaPsi.query.all()
    elif rol == 'Especialista':
        # El especialista solo ve las historias de los pacientes con los que tiene citas agendadas o atendidas
        subquery_pacientes_esp = db.session.query(CitaUni.id_paciente).filter(CitaUni.id_especialista == user_id).subquery()
        lista_historias = HistoriaClinicaPsi.query.join(PacienteUni).filter(
            PacienteUni.id_cliente == cliente_id,
            HistoriaClinicaPsi.id_paciente.in_(subquery_pacientes_esp)
        ).all()
    else:
        # Administradores, Directores y Recepcionistas ven todas las de la empresa cliente
        lista_historias = HistoriaClinicaPsi.query.join(PacienteUni).filter(PacienteUni.id_cliente == cliente_id).all()

    return render_template('historias.html', historias=lista_historias)


@clinica_bp.route('/historias/nueva', methods=['GET', 'POST'])
@login_required
@role_required('Superadmin', 'Director', 'Administrador', 'Especialista')
def crear_historia():
    """Apertura una nueva historia clínica vinculada a un paciente de la organización"""
    cliente_id = session.get('id_cliente')

    if request.method == 'POST':
        id_paciente = request.form.get('id_paciente')
        
        historia_existente = HistoriaClinicaPsi.query.filter_by(id_paciente=id_paciente).first()
        if historia_existente:
            flash('Este paciente ya tiene una historia clínica aperturada.', 'warning')
            return redirect(url_for('clinica.ver_historia', id_historia=historia_existente.id_historia))

        # Estructurar los datos para los campos JSONB
        json_examen_mental = {"descripcion": request.form.get('examen_mental_estado_actual')}
        json_diagnostico = {
            "codigo": request.form.get('codigo_diagnostico'),
            "descripcion": request.form.get('descripcion_diagnostico')
        }

        nueva_historia = HistoriaClinicaPsi(
            id_cliente=cliente_id,
            id_paciente=id_paciente,
            nro_historia=request.form.get('nro_historia'),
            grado_instruccion=request.form.get('grado_instruccion'),
            ocupacion_actual=request.form.get('ocupacion_actual'),
            estado_civil=request.form.get('estado_civil'),
            religion=request.form.get('religion'),
            nombre_acompanante=request.form.get('nombre_acompanante'),
            parentesco_acompanante=request.form.get('parentesco_acompanante'),
            
            motivo_consulta=request.form.get('motivo_consulta'),
            tiempo_enfermedad=request.form.get('tiempo_enfermedad'),
            sintomatologia_principal=request.form.get('sintomatologia_principal'),
            
            antecedentes_personales_psicologicos=request.form.get('antecedentes_personales_psicologicos'),
            antecedentes_medicos_relevantes=request.form.get('antecedentes_medicos_relevantes'),
            antecedentes_familiares=request.form.get('antecedentes_familiares'),
            historia_desarrollo_social=request.form.get('historia_desarrollo_social'),
            
            examen_mental_estado_actual=json_examen_mental,
            diagnostico_cie10_dsm5=json_diagnostico,
            tipo_diagnostico=request.form.get('tipo_diagnostico'),
            
            objetivos_terapeuticos=request.form.get('objetivos_terapeuticos'),
            tipo_intervencion=request.form.get('tipo_intervencion'),
            pronostico=request.form.get('pronostico')
        )
        db.session.add(nueva_historia)
        db.session.commit()
        flash('Ficha e Historia Clínica creada exitosamente.', 'success')
        return redirect(url_for('clinica.ver_historia', id_historia=nueva_historia.id_historia))

    pacientes_sin_historia = PacienteUni.query.filter_by(id_cliente=cliente_id).outerjoin(HistoriaClinicaPsi).filter(HistoriaClinicaPsi.id_historia == None).all()
    return render_template('historia_nueva.html', pacientes_sin_historia=pacientes_sin_historia)


@clinica_bp.route('/historias/<int:id_historia>')
@login_required
def ver_historia(id_historia):
    """Muestra el detalle completo de la historia clínica y sus notas de evolución"""
    historia = HistoriaClinicaPsi.query.get_or_404(id_historia)
    return render_template('historia_detalle.html', historia=historia)


@clinica_bp.route('/sesiones')
@login_required
@role_required('Superadmin', 'Director', 'Administrador', 'Especialista')
def listar_sesiones():
    """Muestra el listado de sesiones de evolución y provee las historias clínicas para el modal"""
    cliente_id = session.get('id_cliente')
    rol = session.get('user_role')
    user_id = session.get('user_id')
    
    if rol == 'Superadmin':
        lista_sesiones = SeguimientoPsi.query.all()
        lista_historias = HistoriaClinicaPsi.query.all()
    elif rol == 'Especialista':
        subquery_pacientes_esp = db.session.query(CitaUni.id_paciente).filter(CitaUni.id_especialista == user_id).subquery()
        lista_sesiones = SeguimientoPsi.query.join(HistoriaClinicaPsi).join(PacienteUni).filter(
            PacienteUni.id_cliente == cliente_id
        ).all()
        # Historias clínicas disponibles para este especialista
        lista_historias = HistoriaClinicaPsi.query.join(PacienteUni).filter(
            PacienteUni.id_cliente == cliente_id,
            HistoriaClinicaPsi.id_paciente.in_(subquery_pacientes_esp)
        ).all()
    else:
        # Administradores y Directores
        lista_sesiones = SeguimientoPsi.query.join(HistoriaClinicaPsi).join(PacienteUni).filter(PacienteUni.id_cliente == cliente_id).all()
        lista_historias = HistoriaClinicaPsi.query.join(PacienteUni).filter(PacienteUni.id_cliente == cliente_id).all()

    return render_template('sesiones.html', sesiones=lista_sesiones, historias=lista_historias)


@clinica_bp.route('/citas/<int:id_cita>/atender', methods=['POST'])
@login_required
@role_required('Superadmin', 'Director', 'Administrador', 'Especialista')
def atender_cita(id_cita):
    """Completa una cita psicológica y registra la evolución en formato S.O.A.P."""
    cita = CitaUni.query.get_or_404(id_cita)
    historia = HistoriaClinicaPsi.query.filter_by(id_paciente=cita.id_paciente).first()
    
    if not historia:
        flash('El paciente no tiene una historia clínica aperturada. Por favor aperture la historia primero.', 'warning')
        return redirect(url_for('clinica.crear_historia'))

    nueva_sesion = SeguimientoPsi(
        id_historia=historia.id_historia,
        id_cita=cita.id_cita,
        id_especialista=session.get('user_id'),
        nota_subjetiva=request.form.get('nota_subjetiva'),
        nota_objetiva=request.form.get('nota_objetiva'),
        apreciacion_clinica=request.form.get('apreciacion_clinica'),
        plan_tareas=request.form.get('plan_tareas'),
        pruebas_aplicadas=request.form.get('pruebas_aplicadas'),
        evaluacion_riesgo=request.form.get('evaluacion_riesgo')
    )
    db.session.add(nueva_sesion)
    
    cita.estado_cita = 'Completada'
    db.session.commit()

    flash(f'Cita #{cita.id_cita} completada y nota S.O.A.P. registrada exitosamente.', 'success')
    return redirect(url_for('clinica.ver_historia', id_historia=historia.id_historia))
