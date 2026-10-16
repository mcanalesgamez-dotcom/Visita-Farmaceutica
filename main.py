from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, Float, ForeignKey, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from datetime import datetime
from typing import List, Optional

# 1. Configuración de la Base de Datos (SQLite local)
DATABASE_URL = "sqlite:///./visita_farmaceutica.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# ==========================================
# 2. MODELOS DE LA BASE DE DATOS (SQLAlchemy)
# ==========================================
class Medico(Base):
    __tablename__ = "medicos"
    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String, index=True)
    especialidad = Column(String)
    direccion = Column(String)
    potencial_prescripcion = Column(String)  # Alta, Media, Baja

class Planificacion(Base):
    __tablename__ = "planificaciones"
    id = Column(Integer, primary_key=True, index=True)
    medico_id = Column(Integer, ForeignKey("medicos.id"))
    fecha_planificada = Column(String)
    estado = Column(String, default="Pendiente")  # Pendiente, Visitado

class Producto(Base):
    __tablename__ = "productos"
    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String, index=True)
    tipo = Column(String)  # Muestra Medica, Material POP, Comercial
    stock = Column(Integer, default=0)

class ReporteVisita(Base):
    __tablename__ = "reportes_visitas"
    id = Column(Integer, primary_key=True, index=True)
    planificacion_id = Column(Integer, ForeignKey("planificaciones.id"))
    fecha_visita = Column(DateTime, default=datetime.utcnow)
    latitud_checkin = Column(Float)
    longitud_checkin = Column(Float)
    comentarios = Column(String)

class MuestraEntregada(Base):
    __tablename__ = "muestras_entregadas"
    id = Column(Integer, primary_key=True, index=True)
    reporte_visita_id = Column(Integer, ForeignKey("reportes_visitas.id"))
    producto_id = Column(Integer, ForeignKey("productos.id"))
    cantidad = Column(Integer)

# Crear todas las tablas en la base de datos de manera automática
Base.metadata.create_all(bind=engine)

# ==========================================
# 3. INICIALIZAR FASTAPI Y DEPENDENCIAS
# ==========================================
app = FastAPI(
    title="Sistema Global de Control de Visita Farmacéutica",
    description="API Backend completa con control de rutas, auditoría GPS e inventario de muestras.",
    version="2.0.0"
)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ==========================================
# 4. ESQUEMAS DE VALIDACIÓN (Pydantic)
# ==========================================
class MedicoCreate(BaseModel):
    nombre: str
    especialidad: str
    direccion: str
    potencial_prescripcion: str

class PlanificacionCreate(BaseModel):
    medico_id: int
    fecha_planificada: str

class ProductoCreate(BaseModel):
    nombre: str
    tipo: str
    stock: int

class MuestraEntregaSchema(BaseModel):
    producto_id: int
    cantidad: int

class ReporteCreate(BaseModel):
    planificacion_id: int
    latitud_checkin: float
    longitud_checkin: float
    comentarios: str
    muestras: Optional[List[MuestraEntregaSchema]] = []

# ==========================================
# 5. ENDPOINTS (Rutas de la API)
# ==========================================

@app.get("/")
def inicio():
    return {"status": "Online", "mensaje": "API de Control Farmacéutico v2 en ejecución"}

# --- MÓDULO DE MÉDICOS ---
@app.post("/medicos/", tags=["Médicos"])
def crear_medico(medico: MedicoCreate, db: Session = Depends(get_db)):
    nuevo_medico = Medico(**medico.model_dump())
    db.add(nuevo_medico)
    db.commit()
    db.refresh(nuevo_medico)
    return nuevo_medico

@app.get("/medicos/", tags=["Médicos"])
def listar_medicos(db: Session = Depends(get_db)):
    return db.query(Medico).all()

# --- MÓDULO DE PRODUCTOS / INVENTARIO ---
@app.post("/productos/", tags=["Inventario de Muestras"])
def crear_producto(producto: ProductoCreate, db: Session = Depends(get_db)):
    nuevo_producto = Producto(**producto.model_dump())
    db.add(nuevo_producto)
    db.commit()
    db.refresh(nuevo_producto)
    return nuevo_producto

@app.get("/productos/", tags=["Inventario de Muestras"])
def listar_productos(db: Session = Depends(get_db)):
    return db.query(Producto).all()

# --- MÓDULO DE PLANIFICACIÓN DE RUTAS ---
@app.post("/planificaciones/", tags=["Planificación de Rutas"])
def crear_planificacion(plan: PlanificacionCreate, db: Session = Depends(get_db)):
    # Validar que el médico exista
    medico = db.query(Medico).filter(Medico.id == plan.medico_id).first()
    if not medico:
        raise HTTPException(status_code=404, detail="Médico no registrado")
    
    nueva_plan = Planificacion(**plan.model_dump())
    db.add(nueva_plan)
    db.commit()
    db.refresh(nueva_plan)
    return nueva_plan

@app.get("/planificaciones/pendientes", tags=["Planificación de Rutas"])
def listar_rutas_pendientes(db: Session = Depends(get_db)):
    return db.query(Planificacion).filter(Planificacion.estado == "Pendiente").all()

# --- MÓDULO DE REPORTES Y DESCUENTO DE STOCK ---
@app.post("/reportes/", tags=["Reportes de Visita y Auditoría"])
def registrar_visita(reporte: ReporteCreate, db: Session = Depends(get_db)):
    # 1. Validar la planificación
    plan = db.query(Planificacion).filter(Planificacion.id == reporte.planificacion_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Planificación de ruta no encontrada")
    
    if plan.estado == "Visitado":
        raise HTTPException(status_code=400, detail="Esta visita ya fue reportada anteriormente")
    
    # 2. Actualizar estado de la ruta
    plan.estado = "Visitado"
    
    # 3. Guardar la auditoría de la visita (GPS y tiempo)
    nuevo_reporte = ReporteVisita(
        planificacion_id=reporte.planificacion_id,
        latitud_checkin=reporte.latitud_checkin,
        longitud_checkin=reporte.longitud_checkin,
        comentarios=reporte.comentarios
    )
    db.add(nuevo_reporte)
    db.commit()
    db.refresh(nuevo_reporte)
    
    # 4. Procesar la entrega de muestras médicas y descontar inventario
    for item in reporte.muestras:
        producto = db.query(Producto).filter(Producto.id == item.producto_id).first()
        if not producto:
            raise HTTPException(status_code=404, detail=True, message=f"El producto con ID {item.producto_id} no existe")
        
        if producto.stock < item.cantidad:
            raise HTTPException(
                status_code=400, 
                detail=f"Stock insuficiente para {producto.nombre}. Stock actual: {producto.stock}"
            )
        
        # Descontar del stock
        producto.stock -= item.cantidad
        
        # Guardar relación histórica de entrega
        entrega = MuestraEntregada(
            reporte_visita_id=nuevo_reporte.id,
            producto_id=item.producto_id,
            cantidad=item.cantidad
        )
        db.add(entrega)
        
    db.commit()
    return {"status": "Éxito", "mensaje": "Visita auditada e inventario actualizado correctamente"}

# --- GERENCIA / DASHBOARD KPIS ---
@app.get("/dashboard/kpis", tags=["Dashboard Gerencial"])
def obtener_metricas(db: Session = Depends(get_db)):
    total_rutas = db.query(Planificacion).count()
    completadas = db.query(Planificacion).filter(Planificacion.estado == "Visitado").count()
    pendientes = total_rutas - completadas
    
    cobertura = (completadas / total_rutas * 100) if total_rutas > 0 else 0.0
    
    return {
        "total_visitas_programadas": total_rutas,
        "visitas_efectivas": completadas,
        "visitas_pendientes": pendientes,
        "tasa_de_cobertura_porcentaje": round(cobertura, 2)
    }
