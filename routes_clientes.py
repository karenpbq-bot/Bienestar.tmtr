from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from models import db, ClienteEmpresa, ModuloSistema, ClienteModulo  # Asegúrate de importar tus modelos o tablas asociadas
from functools import wraps
from datetime import datetime

clientes_bp = Blueprint('clientes', __name__, template_folder='templates')

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

@clientes_bp.route('/clientes', methods=['GET', 'POST'])
@login_required
@role_required('Superadmin')
def gestionar_clientes():
    if request.method == 'POST':
        nombre_marca = request.form.get('nombre_marca', '').strip()
        nombre_empresa = request.form.get('nombre_empresa', '').strip()
        ruc = request.form.get('ruc', '').strip()
        direccion = request.form.get('direccion', '').strip()
        telefono = request.form.get('telefono', '').strip()
        correo_contacto = request.form.get('correo_contacto', '').strip()
        
        # Datos del plan
        tipo_plan = request.form.get('tipo_plan', '').strip()
        costo_plan = request.form.get('costo_plan')
        vigencia_plan = request.form.get('vigencia_plan')
        modo_pago = request.form.get('modo_pago', '').strip()

        # Módulos seleccionados por checkbox
        modulos_seleccionados = request.form.getlist('modulos')

        if not nombre_marca:
            flash('El nombre de la marca o clínica es obligatorio.', 'warning')
        else:
            nuevo_cliente = ClienteEmpresa(
                nombre_marca=nombre_marca,
                nombre_empresa=nombre_empresa if nombre_empresa else None,
                ruc=ruc if ruc else None,
                direccion=direccion if direccion else None,
                telefono=telefono if telefono else None,
                correo_contacto=correo_contacto if correo_contacto else None,
                tipo_plan=tipo_plan if tipo_plan else None,
                costo_plan=float(costo_plan) if costo_plan else 0.0,
                vigencia_plan=datetime.strptime(vigencia_plan, '%Y-%m-%d').date() if vigencia_plan else None,
                modo_pago=modo_pago if modo_pago else None,
                estado_suscripcion='Activo'
            )
            db.session.add(nuevo_cliente)
            db.session.commit()

            # Guardar los módulos contratados en uni_clientes_modulos
            for cod_mod in modulos_seleccionados:
                nuevo_mod = ClienteModulo(id_cliente=nuevo_cliente.id_cliente, codigo_modulo=cod_mod)
                db.session.add(nuevo_mod)
            db.session.commit()

            flash(f'Empresa cliente "{nombre_marca}" registrada exitosamente con sus módulos.', 'success')
        
        return redirect(url_for('clientes.gestionar_clientes'))

    clientes = ClienteEmpresa.query.order_by(ClienteEmpresa.id_cliente.desc()).all()
    modulos_disponibles = ModuloSistema.query.all()
    
    # Mapear los módulos activos de cada cliente para pasarlos a la vista
    for c in clientes:
        c.modulos_activos = [m.codigo_modulo for m in ClienteModulo.query.filter_by(id_cliente=c.id_cliente).all()]

    hoy = datetime.today().date()
    
    return render_template('clientes.html', clientes=clientes, modulos_disponibles=modulos_disponibles, hoy=hoy)

@clientes_bp.route('/clientes/editar/<int:id_cliente>', methods=['POST'])
@login_required
@role_required('Superadmin')
def editar_cliente(id_cliente):
    cliente = ClienteEmpresa.query.get_or_404(id_cliente)
    
    cliente.nombre_marca = request.form.get('nombre_marca', '').strip()
    cliente.nombre_empresa = request.form.get('nombre_empresa', '').strip()
    cliente.ruc = request.form.get('ruc', '').strip()
    cliente.direccion = request.form.get('direccion', '').strip()
    cliente.telefono = request.form.get('telefono', '').strip()
    cliente.correo_contacto = request.form.get('correo_contacto', '').strip()
    cliente.estado_suscripcion = request.form.get('estado_suscripcion', 'Activo')

    cliente.tipo_plan = request.form.get('tipo_plan', '').strip() or None
    
    costo_str = request.form.get('costo_plan')
    cliente.costo_plan = float(costo_str) if costo_str else 0.0

    vigencia_str = request.form.get('vigencia_plan')
    cliente.vigencia_plan = datetime.strptime(vigencia_str, '%Y-%m-%d').date() if vigencia_str else None

    cliente.modo_pago = request.form.get('modo_pago', '').strip() or None

    # Actualizar módulos: Borramos los anteriores y reinsertamos los seleccionados
    modulos_seleccionados = request.form.getlist('modulos')
    ClienteModulo.query.filter_by(id_cliente=id_cliente).delete()
    for cod_mod in modulos_seleccionados:
        nuevo_mod = ClienteModulo(id_cliente=id_cliente, codigo_modulo=cod_mod)
        db.session.add(nuevo_mod)

    db.session.commit()
    flash(f'Datos y módulos de la empresa "{cliente.nombre_marca}" actualizados correctamente.', 'success')
    return redirect(url_for('clientes.gestionar_clientes'))

@clientes_bp.route('/clientes/acciones-masivas', methods=['POST'])
@login_required
@role_required('Superadmin')
def acciones_masivas():
    ids_seleccionados = request.form.getlist('ids_clientes')
    nuevo_estado = request.form.get('nuevo_estado')
    nueva_vigencia = request.form.get('nueva_vigencia')
    
    if not ids_seleccionados:
        flash('No ha seleccionado ninguna empresa para actualizar.', 'warning')
        return redirect(url_for('clientes.gestionar_clientes'))
        
    for id_c in ids_seleccionados:
        cliente = ClienteEmpresa.query.get(id_c)
        if cliente:
            if nuevo_estado:
                cliente.estado_suscripcion = nuevo_estado
            if nueva_vigencia:
                cliente.vigencia_plan = datetime.strptime(nueva_vigencia, '%Y-%m-%d').date()
                
    db.session.commit()
    flash('Se han actualizado las cuentas seleccionadas correctamente.', 'success')
    return redirect(url_for('clientes.gestionar_clientes'))
