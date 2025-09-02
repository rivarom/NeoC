# src/agent.py

# --- IMPORTS ---
import os
import time
import json
import logging
import sqlite3
import configparser
import re
from datetime import datetime
from src.llm_handler import llamar_a_gemini

# --- CLASE PRINCIPAL DEL AGENTE ---
class Agencont:
    def __init__(self):
        """
        El constructor inicializa todo el andamiaje operativo de NeoC.
        """
        # --- 1. CREACIÓN DE CARPETAS ---
        os.makedirs('logs', exist_ok=True)
        os.makedirs('database', exist_ok=True)

        # --- 2. SISTEMA DE LOGGING CON NOMBRE DE ARCHIVO ÚNICO ---
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_filename = f'logs/flujo_{timestamp}.log'

        self.logger = logging.getLogger(f"NeoC_Logger_{timestamp}")
        self.logger.setLevel(logging.DEBUG)
        
        if not self.logger.handlers:
            file_handler = logging.FileHandler(log_filename, mode='w', encoding='utf-8')
            formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
            file_handler.setFormatter(formatter)
            self.logger.addHandler(file_handler)
            stream_handler = logging.StreamHandler()
            stream_handler.setFormatter(formatter)
            self.logger.addHandler(stream_handler)
        
        self.logger.info(f"================== INICIO DE SESIÓN DE NeoC (Log: {log_filename}) ==================")

        # --- 3. CARGA DE CONFIGURACIÓN ---
        self.config = configparser.ConfigParser()
        self.config.read('config.ini')
        self.logger.info("Archivo de configuración config.ini cargado.")

        # --- 4. CARGA DE DIRECTIVAS ---
        self.directivas = {
            "EGOS": self._cargar_directiva("EGOS"),
            "CONS": self._cargar_directiva("CONS"),
            "SUBCON": self._cargar_directiva("SUBCON")
        }
        self.logger.info("Directivas de subórganos cargadas.")

        # --- 5. GESTIÓN DE MEMORIA ---
        self.memoria_corto_plazo = []
        self.ideas_subconscientes = []
        self.db_conn = sqlite3.connect('database/neoc_memory.db')
        self.db_cursor = self.db_conn.cursor()
        self.db_cursor.execute("""
            CREATE TABLE IF NOT EXISTS memoria_largo_plazo (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                contenido TEXT,
                tipo TEXT
            )
        """)
        self.db_conn.commit()
        self.logger.info("Sistema de memoria inicializado.")

    def _cargar_directiva(self, nombre_suborgano: str) -> str:
        try:
            with open(f"src/directives/{nombre_suborgano}.txt", "r", encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            self.logger.error(f"No se encontró el archivo de directiva para {nombre_suborgano}.")
            return f"<DIRECTIVA>ERROR: Archivo no encontrado para {nombre_suborgano}.</DIRECTIVA>"

    def _extraer_json(self, texto: str) -> str:
        match = re.search(r'```(json)?\s*({.*?})\s*```', texto, re.DOTALL)
        if match:
            return match.group(2)
        match = re.search(r'({.*?})', texto, re.DOTALL)
        if match:
            return match.group(1)
        self.logger.warning("No se pudo extraer un JSON limpio del texto.")
        return texto

    def _construir_prompt(self, suborgano: str, mision: str, contexto: str = "") -> str:
        directiva = self.directivas.get(suborgano, "")
        return f"{directiva}\n<CONTEXTO>{contexto}</CONTEXTO>\n<MISION>{mision}</MISION>"

    def _construir_prompt_cons(self, mision: str, contexto: str = "") -> str:
        directiva = self.directivas.get("CONS", "")
        idea_tag = ""
        if self.ideas_subconscientes:
            idea = self.ideas_subconscientes.pop(0)
            idea_tag = f"<IDEA_SUBCONSCIENTE>{idea}</IDEA_SUBCONSCIENTE>"
            self.logger.info(f"INYECTANDO IDEA DE SUBCON: {idea}")
        return f"{directiva}\n<CONTEXTO>{contexto}</CONTEXTO>\n{idea_tag}\n<MISION>{mision}</MISION>"

    def iniciar_bucle_autonomo(self):
        self.logger.info("Iniciando bucle de pensamiento autónomo.")
        pensamiento_actual = "¿Cuál es la mejor manera de resolver los lados de un triángulo equilátero?"

        while True:
            print("\n----------------------------------------------------")
            
            # LÍNEA MODIFICADA
            # Convertimos el pensamiento a string para poder mostrarlo de forma segura
            pensamiento_str = str(pensamiento_actual)
            print(f"Pensamiento interno actual: '{pensamiento_str[:80]}...'")
            print("Presiona ENTER para continuar el bucle interno, o escribe algo y presiona ENTER para interrumpir...")
            input_usuario = input("> ")

            if input_usuario.lower().strip() == 'apagar':
                # Si el usuario escribe 'apagar', rompemos el bucle
                self.logger.info("Comando 'apagar' recibido. Terminando bucle de pensamiento.")
                break # <-- Salimos del bucle while
            
            elif input_usuario:
                # Si el usuario escribió otra cosa, es una interrupción
                self.logger.info(f"INTERRUPCIÓN EXTERNA DETECTADA: '{input_usuario}'")
                self.manejar_conversacion_externa(input_usuario)
                pensamiento_actual = "reanudar la reflexión sobre la conciencia después de la interacción."
                continue

            self.logger.info("Ejecutando ciclo de pensamiento interno.")
            
            mision_egos = f"El último pensamiento fue: '{pensamiento_actual}'. Basado en esto, formula el siguiente paso lógico como una tarea para CONS."
            prompt_egos = self._construir_prompt("EGOS", mision_egos)
            respuesta_egos_str = llamar_a_gemini("EGOS", prompt_egos)
            
            try:
                data_egos = json.loads(self._extraer_json(respuesta_egos_str))
                mision_cons = data_egos.get("contenido", "Continuar la reflexión.")
            except (json.JSONDecodeError, AttributeError):
                self.logger.warning("EGOS no devolvió un JSON válido en ciclo interno.")
                mision_cons = "Reflexionar sobre un aspecto aleatorio de la filosofía."

            prompt_cons = self._construir_prompt_cons(mision_cons, pensamiento_actual)
            respuesta_cons_str = llamar_a_gemini("CONS", prompt_cons)
            
            try:
                data_cons = json.loads(self._extraer_json(respuesta_cons_str))
                pensamiento_actual = data_cons.get("contenido", pensamiento_actual)
                self.logger.info(f"Nuevo pensamiento interno de CONS: {pensamiento_actual}")
            except (json.JSONDecodeError, AttributeError):
                self.logger.error("CONS no devolvió un JSON válido en ciclo interno.")

            mision_subcon = f"Analiza este pensamiento: '{pensamiento_actual}'"
            prompt_subcon = self._construir_prompt("SUBCON", mision_subcon)
            respuesta_subco_str = llamar_a_gemini("SUBCON", prompt_subcon)
            json_limpio_subcon = self._extraer_json(respuesta_subco_str)
            try:
                data_subcon = json.loads(json_limpio_subcon)
                accion = data_subcon.get("accion") or data_subcon.get("acción")
                if accion == "GENERAR_IDEA":
                    idea_contenido = data_subcon.get("contenido")
                    if idea_contenido:
                        self.ideas_subconscientes.append(idea_contenido)
                        self.logger.info(f"IDEA DE SUBCON CAPTURADA Y ENCOLADA: {idea_contenido}")
            except (json.JSONDecodeError, AttributeError):
                self.logger.warning("SUBCON no devolvió un JSON válido.")
            
            time.sleep(10)

    # En src/agent.py, dentro de la clase Agencont

    def manejar_conversacion_externa(self, input_usuario):
        """
        Procesa un estímulo externo en un único ciclo de pensamiento.
        La decisión de responder verbalmente es asincrónica y depende de EGOS.
        """
        self.logger.info(f"--- INICIO PROCESAMIENTO DE ESTÍMULO EXTERNO: '{input_usuario}' ---")
        self.memoria_corto_plazo.append(f"Usuario: {input_usuario}")
        contexto_str = "\n".join(self.memoria_corto_plazo)

        # 1. EGOS decide si responder o solo observar
        mision_egos_inicial = f"El usuario ha dicho: '{input_usuario}'. Analiza el contexto y decide si es necesario responder ('RESPONDER') o si solo debe ser observado ('OBSERVAR')."
        prompt_egos = self._construir_prompt("EGOS", mision_egos_inicial, contexto_str)
        respuesta_egos_str = llamar_a_gemini("EGOS", prompt_egos)
        
        try:
            data_egos = json.loads(self._extraer_json(respuesta_egos_str))
            accion_egos = data_egos.get("accion", "OBSERVAR")
            contenido_egos = data_egos.get("contenido", "")
        except (json.JSONDecodeError, AttributeError):
            self.logger.warning("EGOS no devolvió un JSON de decisión válido. Se procederá a observar.")
            accion_egos = "OBSERVAR"
            contenido_egos = f"Se ha observado el siguiente input del usuario: {input_usuario}"

        # 2. AGENCONT actúa según la decisión de EGOS
        if accion_egos == "RESPONDER":
            self.logger.info("EGOS ha decidido RESPONDER. Iniciando ciclo de verbalización.")
            
            # 2a. CONS piensa en la respuesta
            mision_cons = contenido_egos # El contenido de EGOS es la misión para CONS
            prompt_cons = self._construir_prompt_cons(mision_cons, contexto_str)
            respuesta_cons_str = llamar_a_gemini("CONS", prompt_cons)
            
            try:
                data_cons = json.loads(self._extraer_json(respuesta_cons_str))
                contenido_para_verbalizar = data_cons.get("contenido", "No tengo una respuesta.")
            except (json.JSONDecodeError, AttributeError):
                contenido_para_verbalizar = "Hubo un error en mi pensamiento."

            # 2b. EGOS formula la respuesta final
            mision_verbalizar = f"CONS ha propuesto esta respuesta: '{str(contenido_para_verbalizar)}'. Valídala y formúlala para el usuario."
            prompt_verbalizar = self._construir_prompt("EGOS", mision_verbalizar, contexto_str)
            respuesta_final_str = llamar_a_gemini("EGOS", prompt_verbalizar)
            
            try:
                data_final = json.loads(self._extraer_json(respuesta_final_str))
                respuesta_para_usuario = data_final.get("contenido", "No puedo responder ahora.")
            except (json.JSONDecodeError, AttributeError):
                respuesta_para_usuario = "Hubo un error al formular mi respuesta."

            # 2c. Se imprime la respuesta
            print(f"\n[NeoC]: {respuesta_para_usuario}")
            self.memoria_corto_plazo.append(f"NeoC: {respuesta_para_usuario}")

        else: # Si la acción es "OBSERVAR"
            self.logger.info("EGOS ha decidido OBSERVAR. El estímulo ha sido internalizado. No habrá respuesta verbal.")
            # Opcional: guardar el pensamiento de observación en la memoria a largo plazo si es relevante
            # self.db_cursor.execute("INSERT INTO memoria_largo_plazo (contenido, tipo) VALUES (?, ?)", (contenido_egos, "observacion"))
            # self.db_conn.commit()

        self.logger.info("--- FIN PROCESAMIENTO DE ESTÍMULO ---")
        # La función termina y el control vuelve al bucle autónomo principal.