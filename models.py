from datetime import datetime, timezone, timedelta
import random
import string

def get_peru_time():
    peru_tz = timezone(timedelta(hours=-5))
    return datetime.now(peru_tz)

def generar_codigo(longitud=5):
    """Genera un código aleatorio alfanumérico (letras mayúsculas y números)"""
    caracteres = string.ascii_uppercase + string.digits
    return ''.join(random.choice(caracteres) for _ in range(longitud))

from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

# ===========================================================================
# 1. TABLAS UNIVERSALES O GENERALES (SaaS Multi-Tenant: prefijo uni_)
# ===========================================================================

class ClienteEmpresa(db.Model):
    """Control centralizado de cada consultorio o clínica cliente (Psicología, Odontología, Medicina)"""
    __tablename__ = 'uni_clientes'

    id_cliente = db.Column(db.Integer, primary_key=True, autoincrement=True)
    codigo_invitacion_5d = db.Column(db.String(5), unique=True, nullable=False, index=True, default=lambda: generar_codigo(5))
    tipo_especialidad = db.Column(db.String(50), nullable=False, default='Psicología')
    estado = db.Column(db.Boolean, default=True)

    # Información Comercial y de Marca
    nombre_empresa = db.Column(db.String(150), nullable=True)
    nombre_marca = db.Column(db.String(100), nullable=False)
    ruc = db.Column(db.String(20), unique=True, nullable=True)
    direccion = db.Column(db.String(255), nullable=True)
    telefono = db.Column(db.String(50), nullable=True)
    correo_contacto = db.Column(db.String(120), nullable=True)
    logo_url = db.Column(db.String(255), nullable=True) # Supabase Storage

    # Datos de Contacto y Representante
    representante = db.Column(db.String(150), nullable=True)
    contacto_correo = db.Column(db.String(120), nullable=True)
    contacto_telefono = db.Column(db.String(20), nullable=True)

    # Gestión de Planes y Facturación
    tipo_plan = db.Column(db.String(50), nullable=True)
    vigencia_plan = db.Column(db.Date, nullable=True)
    costo_plan = db.Column(db.Numeric(10, 2), nullable=True)
    modo_pago = db.Column(db.String(50), nullable=True)
    estado_suscripcion = db.Column(db.String(20), default='Activo')
    fecha_creacion = db.Column(db.DateTime(timezone=True), default=get_peru_time)

    # Relaciones Multi-Tenant
    usuarios = db.relationship('UsuarioUni', backref='empresa', lazy=True, cascade="all, delete-orphan")
    pacientes = db.relationship('PacienteUni', backref='empresa', lazy=True, cascade="all, delete-orphan")
    especialistas = db.relationship('EspecialistaUni', backref='empresa', lazy=True, cascade="all, delete-orphan")
    disponibilidades = db.relationship('DisponibilidadUni', backref='empresa', lazy=True, cascade="all, delete-orphan")
    citas = db.relationship('CitaUni', backref='empresa', lazy=True, cascade="all, delete-orphan")

    def __repr__(self):
        return f"<ClienteEmpresa {self.nombre_marca} ({self.codigo_invitacion_5d})>"


class UsuarioUni(db.Model):
    """Personal administrativo, directivo y de recepción (Superadmin, Director, Administrador, Recepcionista)"""
    __tablename__ = 'uni_usuarios'

    id_usuario = db.Column(db.Integer, primary_key=True, autoincrement=True)
    id_cliente = db.Column(db.Integer, db.ForeignKey('uni_clientes.id_cliente'), nullable=True)
    
    rol = db.Column(db.String(50), nullable=False)
    estado = db.Column(db.Boolean, default=True)

    # Datos Personales
    nombres_apellidos = db.Column(db.String(150), nullable=False)
    dni = db.Column(db.String(20), nullable=True)

    # NUEVO: Campo para almacenar el código de 7 dígitos con el que se dio de alta
    codigo_7d = db.Column(db.String(7), nullable=True)
    
    # Credenciales y Seguridad
    correo = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    recordar_sesion = db.Column(db.Boolean, default=False)

    # Auditoría
    fecha_registro = db.Column(db.DateTime(timezone=True), default=get_peru_time)
    ultimo_acceso = db.Column(db.DateTime(timezone=True), nullable=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f"<UsuarioUni {self.nombres_apellidos} ({self.rol})>"


class EspecialistaUni(db.Model):
    __tablename__ = 'uni_especialistas'
    
    id_especialista = db.Column(db.Integer, primary_key=True)
    id_cliente = db.Column(db.Integer, db.ForeignKey('uni_clientes.id_cliente'))
    id_usuario = db.Column(db.Integer, db.ForeignKey('uni_usuarios.id_usuario'))
    estado = db.Column(db.Boolean, default=True)
    nombre = db.Column(db.String(100))
    apellido = db.Column(db.String(100))
    matricula = db.Column(db.String(50))
    rne = db.Column(db.String(50))  # <-- NUEVO CAMPO RNE AÑADIDO
    especialidades = db.Column(db.JSON)
    telefono = db.Column(db.String(50))
    email = db.Column(db.String(120))
    password_hash = db.Column(db.String(255))

    # Relaciones de Agendamiento
    disponibilidades = db.relationship('DisponibilidadUni', backref='especialista', lazy=True, cascade="all, delete-orphan")
    citas = db.relationship('CitaUni', backref='especialista', lazy=True, cascade="all, delete-orphan")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password) if self.password_hash else False

    def __repr__(self):
        return f"<EspecialistaUni {self.nombre} {self.apellido}>"


class PacienteUni(db.Model):
    """Directorio unificado de pacientes con código de invitación de 7 dígitos"""
    __tablename__ = 'uni_pacientes'

    id_paciente = db.Column(db.Integer, primary_key=True, autoincrement=True)
    id_cliente = db.Column(db.Integer, db.ForeignKey('uni_clientes.id_cliente'), nullable=False)
    id_usuario = db.Column(db.Integer, db.ForeignKey('uni_usuarios.id_usuario'), nullable=True) # <-- ESTA LÍNEA DEBE ESTAR SÍ O SÍ EN MODELS.PY
    codigo_invitacion_7d = db.Column(db.String(7), unique=False, nullable=False, index=True)
    
    # Datos Personales y Demográficos
    nombre = db.Column(db.String(100), nullable=False)
    apellido = db.Column(db.String(100), nullable=False)
    dni = db.Column(db.String(20), unique=True, nullable=False)
    fecha_nac = db.Column(db.Date, nullable=True)
    telefono = db.Column(db.String(20), nullable=True)
    direccion = db.Column(db.String(255), nullable=True)

    # Información Médica de Base
    grupo_sangre = db.Column(db.String(10), nullable=True)
    obra_social = db.Column(db.String(100), nullable=True)
    nro_afiliado = db.Column(db.String(50), nullable=True)
    alergias = db.Column(db.Text, nullable=True)
    antecedentes = db.Column(db.JSON, nullable=True)

    # Credenciales y Seguridad
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    recordar_sesion = db.Column(db.Boolean, default=False)
    creado_en = db.Column(db.DateTime(timezone=True), default=get_peru_time)

    # Relaciones
    historias_clinicas = db.relationship('HistoriaClinicaPsi', backref='paciente_rel', lazy=True, cascade="all, delete-orphan")
    citas = db.relationship('CitaUni', backref='paciente', lazy=True, cascade="all, delete-orphan")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f"<PacienteUni {self.nombre} {self.apellido}>"


# ===========================================================================
# 2. MÓDULO DE AGENDAMIENTO Y CALENDARIO (Prefijo uni_)
# ===========================================================================

class DisponibilidadUni(db.Model):
    """Bloques horarios, plantilla semanal y excepciones de los especialistas"""
    __tablename__ = 'uni_disponibilidad'

    id_disponibilidad = db.Column(db.Integer, primary_key=True, autoincrement=True)
    id_cliente = db.Column(db.Integer, db.ForeignKey('uni_clientes.id_cliente'), nullable=False)
    id_especialista = db.Column(db.Integer, db.ForeignKey('uni_especialistas.id_especialista'), nullable=False)
    
    dia_semana = db.Column(db.String(20), nullable=False) # Lunes, Martes, etc.
    fecha_especifica = db.Column(db.Date, nullable=True) # NUEVO: Para excepciones de días exactos del mes
    bloqueado_todo_el_dia = db.Column(db.Boolean, default=False) # NUEVO: Bloqueo total de jornada
    
    hora_inicio = db.Column(db.Time, nullable=True)
    hora_fin = db.Column(db.Time, nullable=True)
    intervalo_minutos = db.Column(db.Integer, default=45)
    estado = db.Column(db.Boolean, default=True)

    def __repr__(self):
        return f"<Disponibilidad {self.dia_semana} {self.fecha_especifica or 'Base'}>"


class CitaUni(db.Model):
    """Registro central de citas reservadas"""
    __tablename__ = 'uni_citas'

    id_cita = db.Column(db.Integer, primary_key=True, autoincrement=True)
    id_cliente = db.Column(db.Integer, db.ForeignKey('uni_clientes.id_cliente'), nullable=False)
    id_paciente = db.Column(db.Integer, db.ForeignKey('uni_pacientes.id_paciente'), nullable=False)
    id_especialista = db.Column(db.Integer, db.ForeignKey('uni_especialistas.id_especialista'), nullable=False)
    
    fecha_hora_inicio = db.Column(db.DateTime(timezone=True), nullable=False)
    fecha_hora_fin = db.Column(db.DateTime(timezone=True), nullable=False)
    estado_cita = db.Column(db.String(50), nullable=False, default='Programada')
    motivo_reserva = db.Column(db.Text, nullable=True)
    creado_en = db.Column(db.DateTime(timezone=True), default=get_peru_time)

    reprogramaciones = db.relationship('ReprogramacionUni', backref='cita', lazy=True, cascade="all, delete-orphan")

    @property
    def cliente(self):
        return self.paciente

    @property
    def fecha_hora(self):
        return self.fecha_hora_inicio

    @property
    def estado(self):
        return self.estado_cita

    @property
    def motivo(self):
        return self.motivo_reserva

    def __repr__(self):
        return f"<CitaUni #{self.id_cita} Estado:{self.estado_cita}>"


class ReprogramacionUni(db.Model):
    """Historial y auditoría de cambios en las citas"""
    __tablename__ = 'uni_reprogramaciones'

    id_reprogramacion = db.Column(db.Integer, primary_key=True, autoincrement=True)
    id_cita = db.Column(db.Integer, db.ForeignKey('uni_citas.id_cita'), nullable=False)
    id_cliente = db.Column(db.Integer, db.ForeignKey('uni_clientes.id_cliente'), nullable=False)
    
    fecha_hora_anterior = db.Column(db.DateTime(timezone=True), nullable=False)
    fecha_hora_nueva = db.Column(db.DateTime(timezone=True), nullable=False)
    motivo_reprogramacion = db.Column(db.Text, nullable=True)
    realizado_por = db.Column(db.String(150), nullable=True)
    fecha_cambio = db.Column(db.DateTime(timezone=True), default=get_peru_time)

    def __repr__(self):
        return f"<ReprogramacionUni Cita:{self.id_cita}>"


# ===========================================================================
# 3. TABLAS ESPECÍFICAS DE PSICOLOGÍA (Prefijo psi_)
# ===========================================================================

class HistoriaClinicaPsi(db.Model):
    """Historia Clínica Base del Paciente (Anamnesis)"""
    __tablename__ = 'psi_historias_clinicas'

    id_historia = db.Column(db.Integer, primary_key=True, autoincrement=True)
    id_cliente = db.Column(db.Integer, db.ForeignKey('uni_clientes.id_cliente'), nullable=False)
    id_paciente = db.Column(db.Integer, db.ForeignKey('uni_pacientes.id_paciente'), nullable=False, unique=True)
    
    nro_historia = db.Column(db.String(35), nullable=True)
    grado_instruccion = db.Column(db.String(250), nullable=True)
    ocupacion_actual = db.Column(db.String(250), nullable=True) # Ampliado por seguridad
    estado_civil = db.Column(db.String(20), nullable=True)
    religion = db.Column(db.String(30), nullable=True)
    nombre_acompanante = db.Column(db.String(100), nullable=True) 
    parentesco_acompanante = db.Column(db.String(50), nullable=True)
    
    # CAMPOS AMPLIADOS A TEXTO ILIMITADO
    motivo_consulta = db.Column(db.Text, nullable=True)
    tiempo_enfermedad = db.Column(db.String(350), nullable=True)
    sintomatologia_principal = db.Column(db.Text, nullable=True)
    
    antecedentes_personales_psicologicos = db.Column(db.Text, nullable=True)
    antecedentes_medicos_relevantes = db.Column(db.Text, nullable=True)
    antecedentes_familiares = db.Column(db.Text, nullable=True)
    historia_desarrollo_social = db.Column(db.Text, nullable=True)
    
    examen_mental_estado_actual = db.Column(db.JSON, nullable=True)
    diagnostico_cie10_dsm5 = db.Column(db.JSON, nullable=True)
    tipo_diagnostico = db.Column(db.String(350), nullable=True)
    
    objetivos_terapeuticos = db.Column(db.Text, nullable=True)
    tipo_intervencion = db.Column(db.String(350), nullable=True)
    pronostico = db.Column(db.String(250), nullable=True)
    
    fecha_apertura = db.Column(db.DateTime(timezone=True), default=get_peru_time)
    estado_historia = db.Column(db.Boolean, default=True)

    seguimientos = db.relationship('SeguimientoPsi', backref='historia_clinica', cascade='all, delete-orphan')


# NUEVO MODELO PARA CONTROLAR PERMISOS AUTOMÁTICOS DE INTERCONSULTA Y AGENDA
class PermisoHistoriaPsi(db.Model):
    """Autorización para que un especialista acceda a la historia de un paciente"""
    __tablename__ = 'psi_permisos_historia'

    id_permiso = db.Column(db.Integer, primary_key=True, autoincrement=True)
    id_historia = db.Column(db.Integer, db.ForeignKey('psi_historias_clinicas.id_historia'), nullable=False)
    id_especialista = db.Column(db.Integer, db.ForeignKey('uni_especialistas.id_especialista'), nullable=False)
    estado_acceso = db.Column(db.Boolean, default=True)
    origen_permiso = db.Column(db.String(500))
    fecha_otorgamiento = db.Column(db.DateTime(timezone=True), default=get_peru_time)

    # Relaciones para navegar fácilmente
    historia = db.relationship('HistoriaClinicaPsi', backref=db.backref('permisos_asignados', lazy=True, cascade='all, delete-orphan'))
    especialista = db.relationship('EspecialistaUni', backref=db.backref('historias_autorizadas', lazy=True))


class SeguimientoPsi(db.Model):
    """Notas de evolución clínica bajo formato SOAP"""
    __tablename__ = 'psi_seguimiento'

    id_seguimiento = db.Column(db.Integer, primary_key=True, autoincrement=True)
    id_historia = db.Column(db.Integer, db.ForeignKey('psi_historias_clinicas.id_historia'), nullable=False)
    id_cita = db.Column(db.Integer, db.ForeignKey('uni_citas.id_cita'), nullable=True)
    id_especialista = db.Column(db.Integer, db.ForeignKey('uni_especialistas.id_especialista'), nullable=False)
    
    numero_sesion = db.Column(db.Integer, nullable=True)
    fecha_sesion = db.Column(db.DateTime(timezone=True), default=get_peru_time)
    
    nota_subjetiva = db.Column(db.String(500), nullable=True)
    nota_objetiva = db.Column(db.String(500), nullable=True)
    apreciacion_clinica = db.Column(db.String(500), nullable=True)
    plan_tareas = db.Column(db.String(500), nullable=True)
    
    pruebas_aplicadas = db.Column(db.String(500), nullable=True)
    evaluacion_riesgo = db.Column(db.String(50), nullable=True)
    proxima_cita_recomendada = db.Column(db.Date, nullable=True)
    
    firma_digital_cerrada = db.Column(db.Boolean, default=False)
    creado_en = db.Column(db.DateTime(timezone=True), default=get_peru_time)

class Codigo7D(db.Model):
    """Códigos de invitación de 7 dígitos generados por el Administrador"""
    __tablename__ = 'uni_codigos_7d'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    codigo = db.Column(db.String(7), unique=True, nullable=False, index=True)
    rol_destino = db.Column(db.String(50), nullable=False)
    id_cliente = db.Column(db.Integer, db.ForeignKey('uni_clientes.id_cliente'), nullable=False)
    usado = db.Column(db.Boolean, default=False)
    fecha = db.Column(db.DateTime(timezone=True), default=get_peru_time)

    def __repr__(self):
        return f"<Codigo7D {self.codigo} ({self.rol_destino})>"

# ===========================================================================
# 4. CONTROL DE MÓDULOS Y ESPECIALIDADES POR CLIENTE (SaaS Multi-Tenant)
# ===========================================================================

class ModuloSistema(db.Model):
    """Catálogo maestro de módulos disponibles en la plataforma (Psicología, Odontología, Agenda, etc.)"""
    __tablename__ = 'uni_modulos'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    codigo_modulo = db.Column(db.String(50), unique=True, nullable=False)
    nombre_modulo = db.Column(db.String(100), nullable=False)
    descripcion = db.Column(db.Text, nullable=True)

    def __repr__(self):
        return f"<ModuloSistema {self.nombre_modulo} ({self.codigo_modulo})>"


class ClienteModulo(db.Model):
    """Tabla relacional para asignar qué módulos contratados tiene cada clínica/empresa cliente"""
    __tablename__ = 'uni_clientes_modulos'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    id_cliente = db.Column(db.Integer, db.ForeignKey('uni_clientes.id_cliente', ondelete='CASCADE'), nullable=False)
    codigo_modulo = db.Column(db.String(50), db.ForeignKey('uni_modulos.codigo_modulo', ondelete='CASCADE'), nullable=False)

    __table_args__ = (
        db.UniqueConstraint('id_cliente', 'codigo_modulo', name='unique_cliente_modulo'),
    )

    def __repr__(self):
        return f"<ClienteModulo Cliente:{self.id_cliente} Módulo:{self.codigo_modulo}>"
