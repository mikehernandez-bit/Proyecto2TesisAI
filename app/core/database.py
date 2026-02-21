from __future__ import annotations
import logging
from sqlalchemy import create_engine, Column, String, Text, DateTime, JSON
from sqlalchemy.orm import sessionmaker, declarative_base
from sshtunnel import SSHTunnelForwarder
from app.core.config import settings

# ------------------------------------------------
# Manejo de la base de datos con SQLAlchemy y túnel SSH
import urllib.parse

logger = logging.getLogger(__name__)

Base = declarative_base()

# Modelo de la tabla de Proyectos
class ProjectDB(Base):
    __tablename__ = "projects"

    id = Column(String, primary_key=True, index=True)
    title = Column(String)
    prompt_id = Column(String, nullable=True)
    prompt_name = Column(String, nullable=True)
    prompt_template = Column(Text, nullable=True)
    format_id = Column(String, nullable=True)
    format_name = Column(String, nullable=True)
    format_version = Column(String, nullable=True)
    variables = Column(JSON, default={})
    values_data = Column(JSON, default={}) # Evitamos usar 'values' que es palabra reservada en dicts
    status = Column(String, default="draft")
    created_at = Column(String)
    updated_at = Column(String)
    output_file = Column(String, nullable=True)
    error = Column(Text, nullable=True)
    ai_result = Column(JSON, nullable=True)
    run_id = Column(String, nullable=True)
    artifacts = Column(JSON, default=[])

class DatabaseManager:
    def __init__(self):
        self.server = None
        self.engine = None
        self.SessionLocal = None

    def connect(self):
        try:
            logger.info("Abriendo túnel SSH...")
            self.server = SSHTunnelForwarder(
                (settings.SSH_HOST, settings.SSH_PORT),
                ssh_username=settings.SSH_USER,
                ssh_password=settings.SSH_PASSWORD,
                remote_bind_address=(settings.DB_HOST, settings.DB_PORT)
            )
            self.server.start()
            local_port = self.server.local_bind_port
            logger.info(f"Túnel SSH establecido. Puerto local: {local_port}")

            # Codificamos la contraseña para que el símbolo @ no rompa la URL
            encoded_password = urllib.parse.quote_plus(settings.DB_PASSWORD)
            db_url = f"postgresql://{settings.DB_USER}:{encoded_password}@127.0.0.1:{local_port}/{settings.DB_NAME}"
            self.engine = create_engine(db_url)
            self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
            
            # Crear tablas si no existen
            Base.metadata.create_all(bind=self.engine)
            logger.info("Conexión a PostgreSQL exitosa y tablas verificadas.")
            
        except Exception as e:
            logger.error(f"Error conectando a la BD o Túnel SSH: {e}")
            raise

    def disconnect(self):
        if self.engine:
            self.engine.dispose()
        if self.server:
            self.server.stop()
            logger.info("Túnel SSH cerrado.")

    def get_session(self):
        db = self.SessionLocal()
        try:
            yield db
        finally:
            db.close()

db_manager = DatabaseManager()