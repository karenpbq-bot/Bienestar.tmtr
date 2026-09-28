from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from models import db, CitaUni, PacienteUni, EspecialistaUni, UsuarioUni, ReprogramacionUni, DisponibilidadUni, get_peru_time, PermisoHistoriaPsi, HistoriaClinicaPsi
from datetime import datetime, timedelta
from routes_auth import login_required, role_required

agenda_bp = Blueprint('agenda', __name__)

@agenda_bp.route('/citas', methods=['GET', 'POST'])
@login_required
def gestionar_citas():
    """Gestiona el listado y la creación de citas unificando pacientes y especialistas de ambas tablas"""
    cliente_id = session.get('id_cliente')
    rol = session.get('user_role')
    
    if request.method == 'POST':
        id_paciente = request.form.get('id_paciente')
        id_especialista = request.form.get('id_especialista')
            
        # BLINDAJE: Si es Especialista y el select HTML está deshabilitado/oculto, forzamos su ID
        if rol == 'Especialista' and not id_especialista:
            id_especialista = session.get('user_id')

        fecha_hora_str = request.form.get('fecha_hora_inicio')
        motivo = request.form.get('motivo_reserva', '')

        try:
            fecha_hora_inicio = datetime.strptime(fecha_hora_str, '%Y-%m-%dT%H:%M')
            fecha_hora_fin = fecha_hora_inicio + timedelta(minutes=45)

            solapada = CitaUni.query.filter(
                CitaUni.id_especialista == int(id_especialista),
                CitaUni.estado_cita != 'Cancelada',
                CitaUni.fecha_hora_inicio < fecha_hora_fin,
                CitaUni.fecha_hora_fin > fecha_hora_inicio
            ).first()

            if solapada:
                flash('⚠️ Conflicto de horario: El especialista ya cuenta con una cita activa en este rango de tiempo.', 'danger')
                return redirect(url_for('agenda.gestionar_citas'))

            nueva_cita = CitaUni(
                id_cliente=cliente_id,
                id_paciente=int(id_paciente),
                id_especialista=int(id_especialista),
                fecha_hora_inicio=fecha_hora_inicio,
                fecha_hora_fin=fecha_hora_fin,
                estado_cita='Programada',
                motivo_reserva=motivo
            )
            db.session.add(nueva_cita)
            db.session.commit()
            
            # --- LÓGICA AUTOMÁTICA: OTORGAR ACCESO A LA HISTORIA ---
            historia = HistoriaClinicaPsi.query.filter_by(id_paciente=int(id_paciente)).first()
            if historia:
                permiso_existente = PermisoHistoriaPsi.query.filter_by(
                    id_historia=historia.id_historia,
                    id_especialista=int(id_especialista)
                ).first()

                if not permiso_existente:
                    nuevo_permiso = PermisoHistoriaPsi(
                        id_historia=historia.id_historia,
                        id_especialista=int(id_especialista),
                        estado_acceso=True,
                        origen_permiso=f"Generado automáticamente por Cita #{nueva_cita.id_cita}",
                        fecha_otorgamiento=get_peru_time()
                    )
                    db.session.add(nuevo_permiso)
                    db.session.commit()
            
            flash('Cita programada con éxito.', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Error al agendar cita: {str(e)}', 'danger')

        return redirect(url_for('agenda.gestionar_citas'))

    # Filtrado Multi-Tenant para el listado de citas
    if rol == 'Superadmin':
        lista_citas = CitaUni.query.order_by(CitaUni.fecha_hora_inicio.desc()).all()
    elif rol == 'Especialista':
        id_especialista = session.get('user_id')
        lista_citas = CitaUni.query.filter_by(id_cliente=cliente_id, id_especialista=id_especialista).order_by(CitaUni.fecha_hora_inicio.desc()).all()
    else:
        lista_citas = CitaUni.query.filter_by(id_cliente=cliente_id).order_by(CitaUni.fecha_hora_inicio.desc()).all()

    # UNIFICACIÓN TOTAL: Capturar pacientes de ambas tablas (PacienteUni y UsuarioUni con rol Paciente)
    pacientes_tabla = PacienteUni.query.filter_by(id_cliente=cliente_id).all()
    pacientes_usuarios = UsuarioUni.query.filter_by(id_cliente=cliente_id, rol='Paciente').all()
    
    ## 1. Cargar todos los pacientes de la clínica actual para que cualquier rol pueda seleccionarlos
    pacientes = PacienteUni.query.filter_by(id_cliente=cliente_id).all()
    
    # 2. Control de especialistas en el selector del formulario:
    # - Si es Especialista: solo se ve a sí mismo en la lista para evitar agendar a nombre de otros.
    # - Si es Superadmin, Administrador, Director o Recepcionista: ve a todos los especialistas de la clínica.
    if rol == 'Especialista':
        especialistas = EspecialistaUni.query.filter_by(id_cliente=cliente_id, id_especialista=session.get('user_id')).all()
    else:
        especialistas = EspecialistaUni.query.filter_by(id_cliente=cliente_id).all()

    return render_template('citas.html', citas=lista_citas, pacientes=pacientes, especialistas=especialistas)


@agenda_bp.route('/citas/<int:id_cita>/estado', methods=['POST'])
@login_required
@role_required('Superadmin', 'Director', 'Administrador', 'Recepcionista', 'Especialista')
def cambiar_estado_cita(id_cita):
    """Permite actualizar el estado de una cita y auditar permisos de historia clínica"""
    cita = CitaUni.query.get_or_404(id_cita)
    nuevo_estado = request.form.get('estado_cita')
    
    if nuevo_estado in ['Programada', 'Completada', 'Cancelada', 'No asistió']:
        cita.estado_cita = nuevo_estado
        db.session.commit()

        # --- LÓGICA AUTOMÁTICA: REVOCACIÓN DE ACCESO POR CANCELACIÓN ---
        if nuevo_estado == 'Cancelada':
            # Verificar si existen otras citas válidas (históricas o futuras) entre este doctor y paciente
            otras_citas = CitaUni.query.filter(
                CitaUni.id_paciente == cita.id_paciente,
                CitaUni.id_especialista == cita.id_especialista,
                CitaUni.id_cita != cita.id_cita,
                CitaUni.estado_cita.in_(['Programada', 'Completada', 'No asistió'])
            ).first()

            # Si no hay historial clínico previo comprobable, revocamos el acceso a la historia
            if not otras_citas:
                historia = HistoriaClinicaPsi.query.filter_by(id_paciente=cita.id_paciente).first()
                if historia:
                    permiso = PermisoHistoriaPsi.query.filter_by(
                        id_historia=historia.id_historia,
                        id_especialista=cita.id_especialista
                    ).first()
                    if permiso:
                        db.session.delete(permiso)
                        db.session.commit()

        flash(f'El estado de la cita #{cita.id_cita} ha sido actualizado a: {nuevo_estado}', 'success')
    else:
        flash('Estado no válido.', 'warning')
        
    return redirect(url_for('agenda.gestionar_citas'))


@agenda_bp.route('/citas/<int:id_cita>/reprogramar', methods=['POST'])
@login_required
@role_required('Superadmin', 'Director', 'Administrador', 'Recepcionista', 'Especialista')

def reprogramar_cita(id_cita):
    """Permite cambiar la fecha/hora de una cita existente"""
    cita = CitaUni.query.get_or_404(id_cita)
    nueva_fecha_str = request.form.get('nueva_fecha_hora')
    motivo = request.form.get('motivo_reprogramacion', 'Reprogramación de cita')

    try:
        nueva_inicio = datetime.strptime(nueva_fecha_str, '%Y-%m-%dT%H:%M')
        duracion = cita.fecha_hora_fin - cita.fecha_hora_inicio
        nueva_fin = nueva_inicio + duracion

        solapada = CitaUni.query.filter(
            CitaUni.id_especialista == cita.id_especialista,
            CitaUni.id_cita != cita.id_cita,
            CitaUni.estado_cita != 'Cancelada',
            CitaUni.fecha_hora_inicio < nueva_fin,
            CitaUni.fecha_hora_fin > nueva_inicio
        ).first()

        if solapada:
            flash('⚠️ No se puede reprogramar: El nuevo horario presenta un cruce con otra cita activa.', 'danger')
            return redirect(url_for('agenda.gestionar_citas'))

        reprogramacion = ReprogramacionUni(
            id_cita=cita.id_cita,
            id_cliente=cita.id_cliente,
            fecha_hora_anterior=cita.fecha_hora_inicio,
            fecha_hora_nueva=nueva_inicio,
            motivo_reprogramacion=motivo,
            realizado_por=session.get('user_name', session.get('user_role', 'Sistema'))
        )

        cita.fecha_hora_inicio = nueva_inicio
        cita.fecha_hora_fin = nueva_fin
        cita.estado_cita = 'Programada'

        db.session.add(reprogramacion)
        db.session.commit()
        flash(f'Cita #{cita.id_cita} reprogramada con éxito.', 'success')

    except Exception as e:
        db.session.rollback()
        flash(f'Error al reprogramar la cita: {str(e)}', 'danger')

    return redirect(url_for('agenda.gestionar_citas'))


@agenda_bp.route('/disponibilidad', methods=['GET', 'POST'])
@login_required
def gestionar_disponibilidad():
    """Gestiona la plantilla semanal completa (T1-T4 por día), réplica masiva y excepciones mensuales del especialista"""
    cliente_id = session.get('id_cliente')
    rol = session.get('user_role')
    user_id = session.get('user_id')

    if rol == 'Especialista':
        especialista_id = user_id
    else:
        especialista_id = request.args.get('id_especialista', type=int)

    if request.method == 'POST':
        if not especialista_id:
            flash('Debe seleccionar un especialista.', 'warning')
            return redirect(url_for('agenda.gestionar_disponibilidad'))

        accion = request.form.get('accion')

        try:
            if accion == 'replicar_lunes':
                # Buscar bloques del lunes configurados en base de datos
                lunes_bloques = DisponibilidadUni.query.filter_by(
                    id_especialista=especialista_id,
                    dia_semana='Lunes',
                    fecha_especifica=None
                ).all()

                if not lunes_bloques:
                    flash('Primero debe configurar y guardar al menos un bloque para el día Lunes.', 'warning')
                    return redirect(url_for('agenda.gestionar_disponibilidad', id_especialista=especialista_id))

                dias_semana = ['Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']
                
                # Eliminar plantillas anteriores de los demás días para limpiarlos y sobreescribir con el Lunes
                DisponibilidadUni.query.filter(
                    DisponibilidadUni.id_especialista == especialista_id,
                    DisponibilidadUni.dia_semana.in_(dias_semana),
                    DisponibilidadUni.fecha_especifica == None
                ).delete(synchronize_session=False)

                # Replicar cada bloque del lunes a los demás días
                for d in dias_semana:
                    for lb in lunes_bloques:
                        nuevo_reg = DisponibilidadUni(
                            id_cliente=cliente_id,
                            id_especialista=especialista_id,
                            dia_semana=d,
                            hora_inicio=lb.hora_inicio,
                            hora_fin=lb.hora_fin,
                            bloqueado_todo_el_dia=lb.bloqueado_todo_el_dia,
                            intervalo_minutos=lb.intervalo_minutos,
                            estado=True
                        )
                        db.session.add(nuevo_reg)

                db.session.commit()
                flash('¡Horarios del Lunes replicados exitosamente a toda la semana!', 'success')

            elif accion == 'guardar_plantilla_masiva':
                dias_semana = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']

                # 1. Limpiar toda la plantilla semanal base previa del especialista
                DisponibilidadUni.query.filter(
                    DisponibilidadUni.id_especialista == especialista_id,
                    DisponibilidadUni.fecha_especifica == None
                ).delete(synchronize_session=False)

                # 2. Recorrer los días y los turnos T1-T4 enviados desde el formulario HTML
                for dia in dias_semana:
                    dia_lower = dia.lower()
                    bloqueado_dia = True if request.form.get(f'bloquear_{dia_lower}') == 'on' else False

                    if bloqueado_dia:
                        # Guardar un registro indicando que el día entero está bloqueado
                        bloqueo_total = DisponibilidadUni(
                            id_cliente=cliente_id,
                            id_especialista=especialista_id,
                            dia_semana=dia,
                            bloqueado_todo_el_dia=True,
                            estado=True
                        )
                        db.session.add(bloqueo_total)
                    else:
                        # Procesar turnos T1 a T4
                        for turno in ['t1', 't2', 't3', 't4']:
                            h_ini_str = request.form.get(f'{dia_lower}_{turno}_inicio')
                            h_fin_str = request.form.get(f'{dia_lower}_{turno}_fin')

                            if h_ini_str and h_fin_str:
                                h_inicio = datetime.strptime(h_ini_str, '%H:%M').time()
                                h_fin = datetime.strptime(h_fin_str, '%H:%M').time()

                                turno_reg = DisponibilidadUni(
                                    id_cliente=cliente_id,
                                    id_especialista=especialista_id,
                                    dia_semana=dia,
                                    hora_inicio=h_inicio,
                                    hora_fin=h_fin,
                                    bloqueado_todo_el_dia=False,
                                    intervalo_minutos=45,
                                    estado=True
                                )
                                db.session.add(turno_reg)

                db.session.commit()
                flash('Plantilla de disponibilidad semanal guardada correctamente.', 'success')

            elif accion == 'guardar_excepcion':
                fecha_str = request.form.get('exc_fecha')
                bloqueado = True if request.form.get('exc_bloqueado') == '1' else False
                hora_inicio_str = request.form.get('exc_inicio')
                hora_fin_str = request.form.get('exc_fin')

                if fecha_str:
                    fecha_obj = datetime.strptime(fecha_str, '%Y-%m-%d').date()
                    h_inicio = datetime.strptime(hora_inicio_str, '%H:%M').time() if hora_inicio_str else None
                    h_fin = datetime.strptime(hora_fin_str, '%H:%M').time() if hora_fin_str else None

                    # Buscar si ya existe una excepción para esa fecha exacta
                    reg = DisponibilidadUni.query.filter_by(
                        id_especialista=especialista_id,
                        fecha_especifica=fecha_obj
                    ).first()

                    if reg:
                        reg.hora_inicio = h_inicio
                        reg.hora_fin = h_fin
                        reg.bloqueado_todo_el_dia = bloqueado
                    else:
                        nueva_exc = DisponibilidadUni(
                            id_cliente=cliente_id,
                            id_especialista=especialista_id,
                            dia_semana='Excepción',
                            fecha_especifica=fecha_obj,
                            hora_inicio=h_inicio,
                            hora_fin=h_fin,
                            bloqueado_todo_el_dia=bloqueado,
                            estado=True
                        )
                        db.session.add(nueva_exc)

                    db.session.commit()
                    flash(f'Excepción para el día {fecha_str} registrada con éxito.', 'success')

        except Exception as e:
            db.session.rollback()
            flash(f'Error al procesar la disponibilidad: {str(e)}', 'danger')

        return redirect(url_for('agenda.gestionar_disponibilidad', id_especialista=especialista_id))

    # Cargar datos para la vista
    especialistas = EspecialistaUni.query.filter_by(id_cliente=cliente_id).all()
    plantilla_base = []
    excepciones = []

    if especialista_id:
        plantilla_base = DisponibilidadUni.query.filter_by(id_especialista=especialista_id, fecha_especifica=None).all()
        excepciones = DisponibilidadUni.query.filter(
            DisponibilidadUni.id_especialista == especialista_id,
            DisponibilidadUni.fecha_especifica != None
        ).all()

    return render_template(
        'disponibilidad.html',
        especialistas=especialistas,
        plantilla_base=plantilla_base,
        excepciones=excepciones,
        especialista_activo=especialista_id
    )

@agenda_bp.route('/disponibilidad/eliminar/<int:id_disponibilidad>', methods=['POST'])
@login_required
@role_required('Superadmin', 'Director', 'Administrador', 'Especialista')
def eliminar_disponibilidad(id_disponibilidad):
    """Permite eliminar un intervalo o bloque horario específico"""
    bloque = DisponibilidadUni.query.get_or_404(id_disponibilidad)
    especialista_id = bloque.id_especialista
    
    db.session.delete(bloque)
    db.session.commit()
    
    flash('Intervalo horario eliminado correctamente.', 'success')
    return redirect(url_for('agenda.gestionar_disponibilidad', id_especialista=especialista_id))
