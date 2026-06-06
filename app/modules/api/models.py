from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.services.maestria_payload_mapper import map_maestria_values, normalize_maestria_details


class PromptBlock(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    block_id: Optional[str] = None
    header: str = ""
    cabecera: str = ""
    label: str = ""
    instructions: str = ""
    required_variables: List[str] = Field(default_factory=list)
    required: bool = True
    legacy_prompt_id: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def normalize_legacy_shape(cls, data: Any) -> Any:
        if data is None:
            return {}
        if not isinstance(data, dict):
            return data
        remapped = dict(data)
        if "header" not in remapped:
            remapped["header"] = (
                remapped.get("cabecera")
                or remapped.get("titulo_cabecera")
                or remapped.get("header")
                or remapped.get("name")
                or remapped.get("label")
                or ""
            )
        remapped["cabecera"] = (
            remapped.get("cabecera")
            or remapped.get("header")
            or remapped.get("titulo_cabecera")
            or remapped.get("name")
            or remapped.get("label")
            or ""
        )
        if "label" not in remapped:
            remapped["label"] = (
                remapped.get("label")
                or remapped.get("header")
                or remapped.get("cabecera")
                or remapped.get("titulo_cabecera")
                or remapped.get("name")
                or ""
            )
        if "instructions" not in remapped:
            remapped["instructions"] = (
                remapped.get("instrucciones_ia") or remapped.get("instruction") or remapped.get("instructions") or ""
            )
        if "required_variables" not in remapped:
            variables = remapped.get("variables_locales")
            if not isinstance(variables, list):
                variables = remapped.get("variables")
            remapped["required_variables"] = variables if isinstance(variables, list) else []
        if "block_id" not in remapped:
            remapped["block_id"] = (
                remapped.get("block_id")
                or remapped.get("id")
                or remapped.get("numero_prompt")
                or remapped.get("legacy_prompt_id")
            )
        if "legacy_prompt_id" not in remapped and remapped.get("numero_prompt") is not None:
            remapped["legacy_prompt_id"] = str(remapped.get("numero_prompt"))
        return remapped


class PromptSection(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    section_id: str
    section_path: str
    section_title: str = ""
    parent_section_path: str = ""
    section_level: int = 1
    section_order: int = 0
    optional: bool = False
    default_selected: bool = True
    source_hints: str = ""
    blocks: List[PromptBlock] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def normalize_legacy_shape(cls, data: Any) -> Any:
        if data is None:
            return {}
        if not isinstance(data, dict):
            return data
        remapped = dict(data)
        legacy_name = str(remapped.get("capitulo_nombre") or remapped.get("name") or "").strip()
        legacy_title = str(remapped.get("titulo_cabecera") or legacy_name or "").strip()

        if "section_id" not in remapped:
            remapped["section_id"] = str(
                remapped.get("sectionId")
                or remapped.get("section_id")
                or remapped.get("id")
                or remapped.get("numero_prompt")
                or ""
            )
        if "section_path" not in remapped:
            remapped["section_path"] = str(
                remapped.get("path") or remapped.get("section_path") or legacy_title or legacy_name
            )
        if "section_title" not in remapped:
            remapped["section_title"] = str(
                remapped.get("section_title")
                or remapped.get("title")
                or remapped.get("titulo_cabecera")
                or remapped.get("name")
                or ""
            )
        if "parent_section_path" not in remapped:
            remapped["parent_section_path"] = str(
                remapped.get("sectionParentPath") or remapped.get("parent_section_path") or ""
            )
        if "section_level" not in remapped:
            remapped["section_level"] = int(
                remapped.get("sectionLevel") or remapped.get("section_level") or remapped.get("order") or 1
            )
        if "section_order" not in remapped:
            remapped["section_order"] = int(remapped.get("sectionOrder") or remapped.get("section_order") or 0)
        if "source_hints" not in remapped:
            remapped["source_hints"] = str(remapped.get("instruction") or remapped.get("source_hints") or "")
        if "blocks" not in remapped:
            instructions = remapped.get("instruction") or remapped.get("instrucciones_ia") or ""
            variables = remapped.get("variables_locales")
            if not isinstance(variables, list):
                variables = remapped.get("variables")
            remapped["blocks"] = (
                [
                    {
                        "block_id": remapped.get("section_id") or remapped.get("numero_prompt"),
                        "header": legacy_title or legacy_name or "Prompt principal",
                        "cabecera": legacy_title or legacy_name or "Prompt principal",
                        "label": legacy_title or legacy_name or "Prompt principal",
                        "instructions": instructions,
                        "required_variables": variables if isinstance(variables, list) else [],
                        "required": True,
                    }
                ]
                if instructions or variables
                else []
            )
        return remapped


class PromptIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    name: str = Field(..., min_length=1)
    doc_type: str = "Tesis Completa"
    is_active: bool = True
    format_id: Optional[str] = None
    format_name: Optional[str] = None
    format_version: Optional[str] = None
    system_instruction: str = Field("", description="Instrucciones globales de estilo")
    required_metadata: List[str] = Field(default_factory=list)
    sections: List[PromptSection] = Field(default_factory=list)
    variables: List[str] = Field(default_factory=list)
    template: str = ""

    @model_validator(mode="before")
    @classmethod
    def normalize_aliases(cls, data: Any) -> Any:
        if data is None:
            return {}
        if not isinstance(data, dict):
            return data
        remapped = dict(data)
        aliases = {
            "docType": "doc_type",
            "formatId": "format_id",
            "formatName": "format_name",
            "formatVersion": "format_version",
            "systemInstruction": "system_instruction",
            "requiredMetadata": "required_metadata",
        }
        for src, dst in aliases.items():
            if src in remapped and dst not in remapped:
                remapped[dst] = remapped[src]
        return remapped


class ProjectGenerateIn(BaseModel):
    format_id: str
    prompt_id: str
    title: Optional[str] = None
    variables: Dict[str, Any] = Field(default_factory=dict)


class ProjectDraftIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    format_id: Optional[str] = None
    prompt_id: Optional[str] = None
    title: Optional[str] = None
    variables: Dict[str, Any] = Field(default_factory=dict)
    format_name: Optional[str] = None
    format_version: Optional[str] = None
    system_instruction: Optional[str] = None
    sections: Optional[List[PromptSection]] = None
    prompt_snapshot: Optional[Dict[str, Any]] = None
    selected_sections: Optional[List[Dict[str, Any]]] = None
    maestria_details: Optional[Dict[str, Any]] = None
    wizard_state: Optional[Dict[str, Any]] = None

    @model_validator(mode="before")
    @classmethod
    def normalize_aliases(cls, data: Any) -> Any:
        if data is None:
            return {}
        if not isinstance(data, dict):
            return data

        remapped = dict(data)
        aliases = {
            "formatId": "format_id",
            "promptId": "prompt_id",
            "values": "variables",
            "formatName": "format_name",
            "formatVersion": "format_version",
            "wizardState": "wizard_state",
            "promptSnapshot": "prompt_snapshot",
            "selectedSections": "selected_sections",
            "maestriaDetails": "maestria_details",
        }
        for src, dst in aliases.items():
            if src in remapped and dst not in remapped:
                remapped[dst] = remapped[src]
        return remapped


class ProjectUpdateIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    format_id: Optional[str] = None
    prompt_id: Optional[str] = None
    title: Optional[str] = None
    variables: Dict[str, Any] = Field(default_factory=dict)
    format_name: Optional[str] = None
    format_version: Optional[str] = None
    status: Optional[str] = None
    system_instruction: Optional[str] = None
    sections: Optional[List[PromptSection]] = None
    prompt_snapshot: Optional[Dict[str, Any]] = None
    selected_sections: Optional[List[Dict[str, Any]]] = None
    maestria_details: Optional[Dict[str, Any]] = None
    wizard_state: Optional[Dict[str, Any]] = None
    reset_generated_state: Optional[bool] = None
    touch_project_timestamp: Optional[bool] = None

    @model_validator(mode="before")
    @classmethod
    def normalize_aliases(cls, data: Any) -> Any:
        if data is None:
            return {}
        if not isinstance(data, dict):
            return data
        remapped = dict(data)
        aliases = {
            "formatId": "format_id",
            "promptId": "prompt_id",
            "values": "variables",
            "formatName": "format_name",
            "formatVersion": "format_version",
            "wizardState": "wizard_state",
            "promptSnapshot": "prompt_snapshot",
            "selectedSections": "selected_sections",
            "maestriaDetails": "maestria_details",
            "resetGeneratedState": "reset_generated_state",
            "touchProjectTimestamp": "touch_project_timestamp",
        }
        for src, dst in aliases.items():
            if src in remapped and dst not in remapped:
                remapped[dst] = remapped[src]
        return remapped


class N8NCallbackIn(BaseModel):
    projectId: str
    runId: Optional[str] = None
    status: Optional[str] = "success"
    aiResult: Dict[str, Any] = Field(default_factory=dict)
    artifacts: List[Dict[str, Any]] = Field(default_factory=list)


class ProviderSelectIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    provider: str = Field(default="mistral")
    model: Optional[str] = None
    fallback_provider: Optional[str] = None
    fallback_model: Optional[str] = None
    mode: str = Field(default="fixed")
    project_id: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def normalize_aliases(cls, data: Any) -> Any:
        if data is None:
            return {}
        if not isinstance(data, dict):
            return data
        remapped = dict(data)
        aliases = {
            "fallbackProvider": "fallback_provider",
            "fallbackModel": "fallback_model",
            "projectId": "project_id",
        }
        for src, dst in aliases.items():
            if src in remapped and dst not in remapped:
                remapped[dst] = remapped[src]
        return remapped


class ProjectGenerateTriggerIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    resume_mode: str = Field(default="auto")

    @model_validator(mode="before")
    @classmethod
    def normalize_aliases(cls, data: Any) -> Any:
        if data is None:
            return {}
        if not isinstance(data, dict):
            return data
        remapped = dict(data)
        if "resumeMode" in remapped and "resume_mode" not in remapped:
            remapped["resume_mode"] = remapped["resumeMode"]
        return remapped

    @model_validator(mode="after")
    def normalize_values(self) -> "ProjectGenerateTriggerIn":
        mode = str(self.resume_mode or "auto").strip().lower()
        if mode not in {"auto", "resume", "restart"}:
            mode = "auto"
        self.resume_mode = mode
        return self


# ---------------------------------------------------------------------------
# Maestría UNAC specific models
# ---------------------------------------------------------------------------


class MaestriaAbreviaturaIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    sigla: str = ""
    significado: str = ""

    @model_validator(mode="before")
    @classmethod
    def normalize_aliases(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        remapped = dict(data)
        aliases = {
            "abbr": "sigla",
            "abreviatura": "sigla",
            "descripcion": "significado",
            "description": "significado",
            "meaning": "significado",
        }
        for src, dst in aliases.items():
            if src in remapped and dst not in remapped:
                remapped[dst] = remapped[src]
        return remapped


class MaestriaMatrizConsistenciaIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    problema_general: str = ""
    objetivo_general: str = ""
    hipotesis_general: str = ""
    variable_independiente: str = ""
    dimensiones_variable_independiente: List[str] = Field(default_factory=list)
    problemas_especificos: List[str] = Field(default_factory=list)
    objetivos_especificos: List[str] = Field(default_factory=list)
    hipotesis_especificas: List[str] = Field(default_factory=list)
    variable_dependiente: str = ""
    dimensiones_variable_dependiente: List[str] = Field(default_factory=list)
    tipo_investigacion: str = ""
    nivel_investigacion: str = ""
    enfoque_investigacion: str = ""
    diseno: str = ""
    poblacion: str = ""
    muestra: str = ""
    tecnicas: str = ""
    instrumentos: str = ""
    procesamiento_datos: str = ""


class MaestriaOperacionalizacionFilaIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    dimension: str = ""
    indicador: str = ""
    indice: str = ""
    metodo_tecnica: str = ""
    tecnica_instrumentos: str = ""

    @model_validator(mode="before")
    @classmethod
    def normalize_aliases(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        remapped = dict(data)
        aliases = {
            "metodoTecnica": "metodo_tecnica",
            "tecnicaInstrumentos": "tecnica_instrumentos",
        }
        for src, dst in aliases.items():
            if src in remapped and dst not in remapped:
                remapped[dst] = remapped[src]
        return remapped


class MaestriaOperacionalizacionIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    variable: str = ""
    definicion_conceptual: str = ""
    definicion_operacional: str = ""
    filas: List[MaestriaOperacionalizacionFilaIn] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def normalize_aliases(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        remapped = dict(data)
        aliases = {
            "definicionConceptual": "definicion_conceptual",
            "definicionOperacional": "definicion_operacional",
            "rows": "filas",
        }
        for src, dst in aliases.items():
            if src in remapped and dst not in remapped:
                remapped[dst] = remapped[src]
        return remapped


class MaestriaDetailsIn(BaseModel):
    """
    Validated input model for UNAC Master's thesis details.
    Used when saving wizard Step 3 data (whether entered via Excel or manually).
    """

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    # Datos generales
    titulo: str = Field(..., min_length=1, description="Título del proyecto (obligatorio)")
    linea_investigacion: Optional[str] = None
    anio: Optional[str] = None
    # El sistema usará automáticamente el año 2026 para la carátula
    lugar_caratula: Optional[str] = None

    # Autor 1
    autor1_nombres: str = Field(..., min_length=1, description="Apellidos y nombres del Autor 1")
    autor1_dni: Optional[str] = None
    autor1_orcid: Optional[str] = None

    # Autor 2 (opcional)
    autor2_nombres: Optional[str] = None
    autor2_dni: Optional[str] = None
    autor2_orcid: Optional[str] = None

    # Asesor
    asesor_nombres: str = Field(..., min_length=1, description="Apellidos y nombres del Asesor")
    asesor_dni: Optional[str] = None
    asesor_orcid: Optional[str] = None

    # Investigación
    lugar_ejecucion: str = Field(..., min_length=1)
    unidad_analisis: str = Field(..., min_length=1)
    tipo: str = Field(..., min_length=1)
    enfoque: str = Field(..., min_length=1)
    diseno_investigacion: str = Field(..., min_length=1)
    nivel_investigacion: Optional[str] = None
    facultad: Optional[str] = Field(None, description="Facultad del proyecto")
    unidad_investigacion: Optional[str] = Field(None, description="Unidad de Investigación de la facultad")


    # Temas OCDE
    tema_ocde_1: str = Field(..., min_length=1, description="Tema OCDE 1 (obligatorio)")
    tema_ocde_2: Optional[str] = None
    tema_ocde_3: Optional[str] = None

    # Datos técnicos para validación de título
    objeto_estudio: str = Field(..., min_length=1)
    variable_independiente: str = Field(..., min_length=1)
    variable_dependiente: str = Field(..., min_length=1)
    poblacion: str = Field(..., min_length=1)
    muestra: str = Field(..., min_length=1)
    lugar: str = Field(..., min_length=1)
    temporal: str = Field(..., min_length=1)
    abreviaturas: List[MaestriaAbreviaturaIn] = Field(default_factory=list)
    matriz_consistencia: MaestriaMatrizConsistenciaIn = Field(default_factory=MaestriaMatrizConsistenciaIn)
    operacionalizacion_vd: MaestriaOperacionalizacionIn = Field(default_factory=MaestriaOperacionalizacionIn)
    operacionalizacion_vi: MaestriaOperacionalizacionIn = Field(default_factory=MaestriaOperacionalizacionIn)

    @model_validator(mode="before")
    @classmethod
    def normalize_aliases(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        remapped = dict(data)
        aliases = {
            "tituloProyecto": "titulo",
            "lineaInvestigacion": "linea_investigacion",
            "anioTexto": "anio",
            "lugarCaratula": "lugar_caratula",
            "autor1Nombres": "autor1_nombres",
            "autor1Dni": "autor1_dni",
            "autor1Orcid": "autor1_orcid",
            "autor2Nombres": "autor2_nombres",
            "autor2Dni": "autor2_dni",
            "autor2Orcid": "autor2_orcid",
            "asesorNombres": "asesor_nombres",
            "asesorDni": "asesor_dni",
            "asesorOrcid": "asesor_orcid",
            "lugarEjecucion": "lugar_ejecucion",
            "unidadAnalisis": "unidad_analisis",
            "disenoInvestigacion": "diseno_investigacion",
            "nivelInvestigacion": "nivel_investigacion",
            "temaOcde1": "tema_ocde_1",
            "temaOcde2": "tema_ocde_2",
            "temaOcde3": "tema_ocde_3",
            "facultad": "facultad",
            "unidadInvestigacion": "unidad_investigacion",
            "objetoEstudio": "objeto_estudio",
            "variableIndependiente": "variable_independiente",
            "variableDependiente": "variable_dependiente",
            "poblacion": "poblacion",
            "muestra": "muestra",
            "lugar": "lugar",
            "temporal": "temporal",
            "matrizConsistencia": "matriz_consistencia",
            "operacionalizacionVD": "operacionalizacion_vd",
            "operacionalizacionVI": "operacionalizacion_vi",
        }
        for src, dst in aliases.items():
            if src in remapped and dst not in remapped:
                remapped[dst] = remapped[src]
        return remapped

    def to_structured_values(self) -> Dict[str, Any]:
        return normalize_maestria_details(self.model_dump(exclude_none=True))

    def to_flat_values(self) -> Dict[str, Any]:
        return map_maestria_values(self.model_dump(exclude_none=True))
