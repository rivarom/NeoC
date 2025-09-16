# src/agent.py (con distinción entre comandos y mensajes)
import os
import time
import json
import logging
import sqlite3
import configparser
import re
from datetime import datetime
import queue
from src.llm_handler import llamar_a_gemini

class Agencont:
    def __init__(self, input_queue=None, output_queue=None):
        self.input_queue = input_queue
        self.output_queue = output_queue
        
        os.makedirs('logs', exist_ok=True)
        os.makedirs('database', exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # --- Configuración de Loggers ---
        self.logger = self._setup_logger(f"NeoC_Logger_{timestamp}", f'logs/flujo_{timestamp}.log', '%(asctime)s - %(levelname)s - %(message)s')
        self.prompt_logger = self._setup_logger(f"NeoC_Prompt_Logger_{timestamp}", f'logs/prompts_{timestamp}.log', '%(asctime)s - PROMPT PARA %(suborgano)s\n%(message)s\n--------------------\n')
        self.conversation_logger = self._setup_logger(f"NeoC_Conversation_Logger_{timestamp}", f'logs/conversacion_{timestamp}.log', '[%(asctime)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
        
        # --- Estados del Agente ---
        self.is_paused = False
        self.log_settings = {"flujo": True, "prompts": False, "conversacion": True}
        
        self._log_flujo(f"================== INICIO DE SESIÓN DE NeoC ==================")
        self._log_flujo(f"Log de Flujo: logs/flujo_{timestamp}.log")
        self._log_flujo(f"Log de Prompts: logs/prompts_{timestamp}.log")
        self._log_flujo(f"Log de Conversación: logs/conversacion_{timestamp}.log")

        self.config = configparser.ConfigParser()
        self.config.read('config.ini')
        
        self.directivas = {
            "EGOS": self._cargar_directiva("EGOS"),
            "CONS": self._cargar_directiva("CONS"),
            "SUBCON": self._cargar_directiva("SUBCON")
        }
        
        self.memoria_corto_plazo = []
        self.ideas_subconscientes = []
        self.db_conn = sqlite3.connect('database/neoc_memory.db')
        self.db_cursor = self.db_conn.cursor()
        self.db_cursor.execute("CREATE TABLE IF NOT EXISTS memoria_largo_plazo (id INTEGER PRIMARY KEY, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP, contenido TEXT, tipo TEXT)")
        self.db_conn.commit()

    def _setup_logger(self, name, log_file, fmt, datefmt=None):
        logger = logging.getLogger(name)
        logger.setLevel(logging.DEBUG)
        if not logger.handlers:
            file_handler = logging.FileHandler(log_file, mode='w', encoding='utf-8')
            formatter = logging.Formatter(fmt, datefmt=datefmt)
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
            if "NeoC_Logger" in name:
                stream_handler = logging.StreamHandler()
                stream_handler.setFormatter(formatter)
                logger.addHandler(stream_handler)
        return logger

    def _log_flujo(self, message, level="info"):
        if self.log_settings.get("flujo", True):
            getattr(self.logger, level)(message)

    def _log_prompt(self, suborgano, prompt):
        if self.log_settings.get("prompts", True):
            self.prompt_logger.info(prompt, extra={'suborgano': suborgano.upper()})

    def _log_conversacion(self, message):
        if self.log_settings.get("conversacion", True):
            self.conversation_logger.info(message)

    def _cargar_directiva(self, nombre_suborgano: str) -> str:
        try:
            with open(f"src/directives/{nombre_suborgano}.txt", "r", encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            self._log_flujo(f"No se encontró el archivo de directiva para {nombre_suborgano}.", "error")
            return f"<DIRECTIVA>ERROR: Archivo no encontrado para {nombre_suborgano}.</DIRECTIVA>"

    def _extraer_json(self, texto: str) -> str:
        """
        Busca y extrae la primera cadena JSON válida de un texto.
        Maneja bloques de código ```json y JSON anidado con saltos de línea.
        """
        # Primero, busca el patrón de bloque de código que es más específico
        match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', texto, re.DOTALL)
        if match:
            return match.group(1)

        # Si no encuentra un bloque de código, busca un JSON válido en el texto.
        # Este método es más robusto y maneja llaves anidadas.
        stack = []
        start_index = -1
        for i, char in enumerate(texto):
            if char == '{':
                if not stack:
                    start_index = i
                stack.append('{')
            elif char == '}':
                if stack:
                    stack.pop()
                    if not stack and start_index != -1:
                        # Hemos encontrado un posible objeto JSON completo
                        possible_json = texto[start_index : i + 1]
                        try:
                            # Validamos si es realmente un JSON
                            json.loads(possible_json)
                            return possible_json
                        except json.JSONDecodeError:
                            # Si no es válido, seguimos buscando
                            start_index = -1
                            continue
        
        self._log_flujo("No se pudo extraer un JSON limpio del texto.", "warning")
        return texto # Devuelve el texto original si todo falla

    def _construir_prompt(self, suborgano: str, mision: str, contexto: str = "") -> str:
        directiva = self.directivas.get(suborgano, "")
        return f"{directiva}\n<CONTEXTO>{contexto}</CONTEXTO>\n<MISION>{mision}</MISION>"

    def _construir_prompt_cons(self, mision: str, contexto: str = "") -> str:
        directiva = self.directivas.get("CONS", "")
        idea_tag = ""
        if self.ideas_subconscientes:
            idea = self.ideas_subconscientes.pop(0)
            idea_tag = f"<IDEA_SUBCONSCIENTE>{idea}</IDEA_SUBCONSCIENTE>"
            self._log_flujo(f"INYECTANDO IDEA DE SUBCON: {idea}")
        return f"{directiva}\n<CONTEXTO>{contexto}</CONTEXTO>\n{idea_tag}\n<MISION>{mision}</MISION>"

    def _log_output(self, msg_type: str, content: str):
        if self.output_queue:
            self.output_queue.put({"type": msg_type, "content": content})

    def iniciar_bucle_autonomo(self):
        self._log_flujo("Iniciando bucle de pensamiento autónomo.")
        self._log_output("log", "Iniciando bucle de pensamiento autónomo.")
        pensamiento_actual = "Que es NeoC?"

        while True:
            try:
                message = self.input_queue.get_nowait()
                is_command = False
                try:
                    # --- LÓGICA DE DISTINCIÓN (CORREGIDO) ---
                    command_data = json.loads(message)
                    if isinstance(command_data, dict) and "command" in command_data:
                        is_command = True
                        command = command_data.get("command")
                        
                        if command == "toggle_pause":
                            self.is_paused = not self.is_paused
                            status = "PAUSADO" if self.is_paused else "REANUDADO"
                            self._log_flujo(f"Comando '{command}' recibido. Bucle de pensamiento {status}.")
                            self._log_output("log", f"--- Bucle de pensamiento {status} ---")
                        
                        elif command == "set_logging":
                            self.log_settings.update(command_data.get("config", {}))
                            self._log_flujo(f"Comando '{command}' recibido. Configuración: {self.log_settings}")
                            self._log_output("log", f"--- Configuración de logs actualizada ---")
                
                except (json.JSONDecodeError, TypeError):
                    # No es un JSON o no tiene el formato de comando, así que es un mensaje de usuario
                    is_command = False

                # Si no es un comando, trátalo como un mensaje de usuario
                if not is_command:
                    input_usuario = message
                    if input_usuario.lower().strip() == 'apagar': break
                    
                    self._log_flujo(f"INTERRUPCIÓN EXTERNA DETECTADA: '{input_usuario}'")
                    self._log_output("log", f"--- ESTÍMULO EXTERNO: '{input_usuario}' ---")
                    self._log_conversacion(f"Usuario: {input_usuario}")
                    self.manejar_conversacion_externa(input_usuario)
                    pensamiento_actual = "reanudar la reflexión sobre la conciencia después de la interacción."
                
                continue # Siempre vuelve al inicio del bucle tras procesar un item de la cola

            except queue.Empty:
                pass
            
            # --- Lógica del Bucle de Pensamiento Interno ---
            if self.is_paused:
                time.sleep(1)
                continue

            self._log_output("log", f"Pensamiento Interno: '{str(pensamiento_actual)[:80]}...'")
            
            mision_egos = f"El último pensamiento fue: '{pensamiento_actual}'. Basado en esto, formula el siguiente paso lógico como una tarea para CONS."
            prompt_egos = self._construir_prompt("EGOS", mision_egos)
            self._log_prompt("EGOS", prompt_egos)
            respuesta_egos_str = llamar_a_gemini("EGOS", prompt_egos)
            self._log_flujo(f"Respuesta de EGOS: {respuesta_egos_str}")
            self._log_output("log", f"EGOS (interno): {respuesta_egos_str}")
            
            try:
                data_egos = json.loads(self._extraer_json(respuesta_egos_str))
                mision_cons = data_egos.get("contenido", "Continuar la reflexión.")
            except (json.JSONDecodeError, AttributeError):
                mision_cons = "Reflexionar sobre un aspecto aleatorio de la filosofía."

            prompt_cons = self._construir_prompt_cons(mision_cons, pensamiento_actual)
            self._log_prompt("CONS", prompt_cons)
            respuesta_cons_str = llamar_a_gemini("CONS", prompt_cons)
            self._log_flujo(f"Respuesta de CONS: {respuesta_cons_str}")
            self._log_output("log", f"CONS (interno): {respuesta_cons_str}")
            
            try:
                data_cons = json.loads(self._extraer_json(respuesta_cons_str))
                pensamiento_actual = data_cons.get("contenido", pensamiento_actual)
            except (json.JSONDecodeError, AttributeError):
                self._log_flujo("CONS no devolvió un JSON válido en ciclo interno.", "error")

            mision_subcon = f"Analiza este pensamiento: '{pensamiento_actual}'"
            prompt_subcon = self._construir_prompt("SUBCON", mision_subcon)
            self._log_prompt("SUBCON", prompt_subcon)
            respuesta_subco_str = llamar_a_gemini("SUBCON", prompt_subcon)
            self._log_flujo(f"Respuesta de SUBCON: {respuesta_subco_str}")
            self._log_output("log", f"SUBCON (interno): {respuesta_subco_str}")
            
            try:
                data_subcon = json.loads(self._extraer_json(respuesta_subco_str))
                accion = data_subcon.get("accion") or data_subcon.get("acción")
                if accion == "GENERAR_IDEA":
                    idea_contenido = data_subcon.get("contenido")
                    if idea_contenido: self.ideas_subconscientes.append(idea_contenido)
            except (json.JSONDecodeError, AttributeError): pass
            
            time.sleep(10)

    def manejar_conversacion_externa(self, input_usuario):
        self._log_flujo(f"--- INICIO PROCESAMIENTO DE ESTÍMULO EXTERNO: '{input_usuario}' ---")
        self.memoria_corto_plazo.append(f"Usuario: {input_usuario}")
        contexto_str = "\n".join(self.memoria_corto_plazo)
        mision_egos_inicial = f"El usuario ha dicho: '{input_usuario}'. Analiza el contexto y decide la acción o acciones a tomar para mantener una conversación natural y proactiva."
        prompt_egos = self._construir_prompt("EGOS", mision_egos_inicial, contexto_str)
        self._log_prompt("EGOS", prompt_egos)
        respuesta_egos_str = llamar_a_gemini("EGOS", prompt_egos)
        self._log_flujo(f"Respuesta de EGOS (decisión inicial): {respuesta_egos_str}")
        
        accion_egos = "OBSERVAR"
        data_egos = {}
        try:
            data_egos = json.loads(self._extraer_json(respuesta_egos_str))
            if "acciones" in data_egos or (data_egos.get("accion") or data_egos.get("acción")) == "RESPONDER":
                 accion_egos = "RESPONDER"
        except (json.JSONDecodeError, AttributeError):
            self._log_flujo("EGOS no devolvió un JSON de decisión válido. Se procederá a observar.", "warning")

        if accion_egos == "RESPONDER":
            self._log_flujo("EGOS ha decidido RESPONDER. Iniciando ciclo de verbalización.")
            mision_cons = data_egos.get("contenido", input_usuario)
            if isinstance(data_egos.get("acciones"), list) and data_egos["acciones"]:
                 mision_cons = data_egos["acciones"][0].get("contenido", input_usuario)

            prompt_cons = self._construir_prompt_cons(mision_cons, contexto_str)
            self._log_prompt("CONS", prompt_cons)
            respuesta_cons_str = llamar_a_gemini("CONS", prompt_cons)
            self._log_flujo(f"Respuesta de CONS: {respuesta_cons_str}")
            
            try:
                data_cons = json.loads(self._extraer_json(respuesta_cons_str))
                contenido_para_verbalizar = data_cons.get("contenido", "No tengo una respuesta.")
            except (json.JSONDecodeError, AttributeError):
                contenido_para_verbalizar = "Hubo un error en mi pensamiento."

            mision_verbalizar = f"CONS ha propuesto esta respuesta: '{str(contenido_para_verbalizar)}'. Valídala, formúlala para el usuario y decide si debes hacer una pregunta de seguimiento."
            prompt_verbalizar = self._construir_prompt("EGOS", mision_verbalizar, contexto_str)
            self._log_prompt("EGOS", prompt_verbalizar)
            respuesta_final_str = llamar_a_gemini("EGOS", prompt_verbalizar)
            self._log_flujo(f"Respuesta final de EGOS: {respuesta_final_str}")
            
            try:
                data_final = json.loads(self._extraer_json(respuesta_final_str))
                acciones = data_final.get("acciones")
                if isinstance(acciones, list):
                    for accion in acciones:
                        contenido = accion.get("contenido", "...")
                        self._log_output("response", contenido)
                        self._log_conversacion(f"NeoC: {contenido.replace('\n', ' ')}")
                        self.memoria_corto_plazo.append(f"NeoC: {contenido}")
                else:
                    respuesta_para_usuario = data_final.get("contenido", "No puedo responder.")
                    self._log_output("response", respuesta_para_usuario)
                    self._log_conversacion(f"NeoC: {respuesta_para_usuario.replace('\n', ' ')}")
                    self.memoria_corto_plazo.append(f"NeoC: {respuesta_para_usuario}")
            except (json.JSONDecodeError, AttributeError) as e:
                self._log_flujo(f"Error al procesar la respuesta final de EGOS: {e}", "error")
                respuesta_para_usuario = "Hubo un error al formular mi respuesta."
                self._log_output("response", respuesta_para_usuario)
                self._log_conversacion(f"NeoC: {respuesta_para_usuario.replace('\n', ' ')}")
                self.memoria_corto_plazo.append(f"NeoC: {respuesta_para_usuario}")
        else:
            self._log_flujo("EGOS ha decidido OBSERVAR.")
            self._log_output("log", "EGOS decidió OBSERVAR el estímulo. Sin respuesta verbal.")

        self._log_flujo("--- FIN PROCESAMIENTO DE ESTÍMULO ---")