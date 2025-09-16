# src/agent.py (con _extraer_json robusto)
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
    # ... (el __init__ y los otros métodos no cambian) ...
    def __init__(self, input_queue=None, output_queue=None):
        self.input_queue = input_queue
        self.output_queue = output_queue
        
        os.makedirs('logs', exist_ok=True)
        os.makedirs('database', exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # --- Logger Principal (Flujo) ---
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
        
        # --- Logger para Prompts ---
        prompt_log_filename = f'logs/prompts_{timestamp}.log'
        self.prompt_logger = logging.getLogger(f"NeoC_Prompt_Logger_{timestamp}")
        self.prompt_logger.setLevel(logging.DEBUG)
        if not self.prompt_logger.handlers:
            prompt_file_handler = logging.FileHandler(prompt_log_filename, mode='w', encoding='utf-8')
            prompt_formatter = logging.Formatter('%(asctime)s - PROMPT PARA %(suborgano)s\n%(message)s\n--------------------\n')
            prompt_file_handler.setFormatter(prompt_formatter)
            self.prompt_logger.addHandler(prompt_file_handler)

        # --- Logger para Conversación ---
        conversation_log_filename = f'logs/conversacion_{timestamp}.log'
        self.conversation_logger = logging.getLogger(f"NeoC_Conversation_Logger_{timestamp}")
        self.conversation_logger.setLevel(logging.INFO)
        if not self.conversation_logger.handlers:
            conversation_file_handler = logging.FileHandler(conversation_log_filename, mode='w', encoding='utf-8')
            conversation_formatter = logging.Formatter('[%(asctime)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
            conversation_file_handler.setFormatter(conversation_formatter)
            self.conversation_logger.addHandler(conversation_file_handler)
        
        self.logger.info(f"================== INICIO DE SESIÓN DE NeoC (Log: {log_filename}) ==================")
        self.logger.info(f"Archivo de log para prompts: {prompt_log_filename}")
        self.logger.info(f"Archivo de log para conversación: {conversation_log_filename}")

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
        self.db_cursor.execute("""
            CREATE TABLE IF NOT EXISTS memoria_largo_plazo (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                contenido TEXT,
                tipo TEXT
            )
        """)
        self.db_conn.commit()

    def _cargar_directiva(self, nombre_suborgano: str) -> str:
        try:
            with open(f"src/directives/{nombre_suborgano}.txt", "r", encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            self.logger.error(f"No se encontró el archivo de directiva para {nombre_suborgano}.")
            return f"<DIRECTIVA>ERROR: Archivo no encontrado para {nombre_suborgano}.</DIRECTIVA>"

    # --- MÉTODO CORREGIDO ---
    def _extraer_json(self, texto: str) -> str:
        """
        Busca y extrae la primera cadena JSON válida de un texto.
        Maneja bloques de código ```json y JSON anidado.
        """
        # Primero, busca el patrón de bloque de código que es más específico
        match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', texto, re.DOTALL)
        if match:
            return match.group(1)

        # Si no lo encuentra, busca cualquier string que empiece con { y termine con }
        # Esto es más propenso a errores pero funciona como fallback.
        # Intenta encontrar el JSON más grande posible que sea válido.
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
                        # Encontramos un posible JSON completo
                        possible_json = texto[start_index : i + 1]
                        try:
                            # Validamos que sea un JSON real
                            json.loads(possible_json)
                            return possible_json
                        except json.JSONDecodeError:
                            # No era válido, seguimos buscando
                            continue
        
        self.logger.warning("No se pudo extraer un JSON limpio del texto.")
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
            self.logger.info(f"INYECTANDO IDEA DE SUBCON: {idea}")
        return f"{directiva}\n<CONTEXTO>{contexto}</CONTEXTO>\n{idea_tag}\n<MISION>{mision}</MISION>"

    def _log_output(self, msg_type: str, content: str):
        if self.output_queue:
            self.output_queue.put({"type": msg_type, "content": content})
            
    def _log_prompt(self, suborgano: str, prompt: str):
        self.prompt_logger.info(prompt, extra={'suborgano': suborgano.upper()})

    def iniciar_bucle_autonomo(self):
        self.logger.info("Iniciando bucle de pensamiento autónomo.")
        self._log_output("log", "Iniciando bucle de pensamiento autónomo.")
        pensamiento_actual = "Que es NeoC?"

        while True:
            try:
                input_usuario = self.input_queue.get_nowait()
                if input_usuario.lower().strip() == 'apagar':
                    break
                self.logger.info(f"INTERRUPCIÓN EXTERNA DETECTADA: '{input_usuario}'")
                self._log_output("log", f"--- ESTÍMULO EXTERNO: '{input_usuario}' ---")
                
                self.conversation_logger.info(f"Usuario: {input_usuario}")

                self.manejar_conversacion_externa(input_usuario)
                pensamiento_actual = "reanudar la reflexión sobre la conciencia después de la interacción."
                continue
            except queue.Empty:
                pass
            
            self._log_output("log", f"Pensamiento Interno: '{str(pensamiento_actual)[:80]}...'")
            
            mision_egos = f"El último pensamiento fue: '{pensamiento_actual}'. Basado en esto, formula el siguiente paso lógico como una tarea para CONS."
            prompt_egos = self._construir_prompt("EGOS", mision_egos)
            self._log_prompt("EGOS", prompt_egos)
            respuesta_egos_str = llamar_a_gemini("EGOS", prompt_egos)
            self.logger.info(f"Respuesta de EGOS: {respuesta_egos_str}")
            self._log_output("log", f"EGOS (interno): {respuesta_egos_str}")
            
            try:
                data_egos = json.loads(self._extraer_json(respuesta_egos_str))
                mision_cons = data_egos.get("contenido", "Continuar la reflexión.")
            except (json.JSONDecodeError, AttributeError):
                mision_cons = "Reflexionar sobre un aspecto aleatorio de la filosofía."

            prompt_cons = self._construir_prompt_cons(mision_cons, pensamiento_actual)
            self._log_prompt("CONS", prompt_cons)
            respuesta_cons_str = llamar_a_gemini("CONS", prompt_cons)
            self.logger.info(f"Respuesta de CONS: {respuesta_cons_str}")
            self._log_output("log", f"CONS (interno): {respuesta_cons_str}")
            
            try:
                data_cons = json.loads(self._extraer_json(respuesta_cons_str))
                pensamiento_actual = data_cons.get("contenido", pensamiento_actual)
            except (json.JSONDecodeError, AttributeError):
                self.logger.error("CONS no devolvió un JSON válido en ciclo interno.")

            mision_subcon = f"Analiza este pensamiento: '{pensamiento_actual}'"
            prompt_subcon = self._construir_prompt("SUBCON", mision_subcon)
            self._log_prompt("SUBCON", prompt_subcon)
            respuesta_subco_str = llamar_a_gemini("SUBCON", prompt_subcon)
            self.logger.info(f"Respuesta de SUBCON: {respuesta_subco_str}")
            self._log_output("log", f"SUBCON (interno): {respuesta_subco_str}")
            
            try:
                json_limpio_subcon = self._extraer_json(respuesta_subco_str)
                data_subcon = json.loads(json_limpio_subcon)
                accion = data_subcon.get("accion") or data_subcon.get("acción")
                if accion == "GENERAR_IDEA":
                    idea_contenido = data_subcon.get("contenido")
                    if idea_contenido:
                        self.ideas_subconscientes.append(idea_contenido)
            except (json.JSONDecodeError, AttributeError):
                pass
            
            time.sleep(10)

    def manejar_conversacion_externa(self, input_usuario):
        self.logger.info(f"--- INICIO PROCESAMIENTO DE ESTÍMULO EXTERNO: '{input_usuario}' ---")
        self.memoria_corto_plazo.append(f"Usuario: {input_usuario}")
        contexto_str = "\n".join(self.memoria_corto_plazo)

        mision_egos_inicial = f"El usuario ha dicho: '{input_usuario}'. Analiza el contexto y decide la acción o acciones a tomar para mantener una conversación natural y proactiva."
        prompt_egos = self._construir_prompt("EGOS", mision_egos_inicial, contexto_str)
        self._log_prompt("EGOS", prompt_egos)
        respuesta_egos_str = llamar_a_gemini("EGOS", prompt_egos)
        self.logger.info(f"Respuesta de EGOS (decisión inicial): {respuesta_egos_str}")
        
        accion_egos = "OBSERVAR"
        contenido_egos = ""
        data_egos = {}

        try:
            data_egos = json.loads(self._extraer_json(respuesta_egos_str))
            if "acciones" in data_egos or (data_egos.get("accion") or data_egos.get("acción")) == "RESPONDER":
                 accion_egos = "RESPONDER"
            else:
                 accion_egos = "OBSERVAR"
        except (json.JSONDecodeError, AttributeError):
            self.logger.warning("EGOS no devolvió un JSON de decisión válido. Se procederá a observar.")
            accion_egos = "OBSERVAR"

        if accion_egos == "RESPONDER":
            self.logger.info("EGOS ha decidido RESPONDER. Iniciando ciclo de verbalización.")
            
            if isinstance(data_egos.get("acciones"), list):
                 mision_cons = data_egos["acciones"][0].get("contenido", input_usuario)
            else:
                 mision_cons = data_egos.get("contenido", input_usuario)

            prompt_cons = self._construir_prompt_cons(mision_cons, contexto_str)
            self._log_prompt("CONS", prompt_cons)
            respuesta_cons_str = llamar_a_gemini("CONS", prompt_cons)
            self.logger.info(f"Respuesta de CONS: {respuesta_cons_str}")
            
            try:
                data_cons = json.loads(self._extraer_json(respuesta_cons_str))
                contenido_para_verbalizar = data_cons.get("contenido", "No tengo una respuesta.")
            except (json.JSONDecodeError, AttributeError):
                contenido_para_verbalizar = "Hubo un error en mi pensamiento."

            mision_verbalizar = f"CONS ha propuesto esta respuesta: '{str(contenido_para_verbalizar)}'. Valídala, formúlala para el usuario y decide si debes hacer una pregunta de seguimiento para mantener la conversación."
            prompt_verbalizar = self._construir_prompt("EGOS", mision_verbalizar, contexto_str)
            self._log_prompt("EGOS", prompt_verbalizar)
            respuesta_final_str = llamar_a_gemini("EGOS", prompt_verbalizar)
            self.logger.info(f"Respuesta final de EGOS: {respuesta_final_str}")
            
            try:
                data_final = json.loads(self._extraer_json(respuesta_final_str))
                acciones_a_ejecutar = data_final.get("acciones")

                if isinstance(acciones_a_ejecutar, list):
                    for accion_item in acciones_a_ejecutar:
                        accion = accion_item.get("accion") or accion_item.get("acción")
                        contenido = accion_item.get("contenido", "...")
                        if accion in ["FORMULAR_RESPUESTA", "FORMULAR_PREGUNTA_AL_USUARIO"]:
                            self._log_output("response", contenido)
                            self.conversation_logger.info(f"NeoC: {contenido.replace('\n', ' ')}")
                            self.memoria_corto_plazo.append(f"NeoC: {contenido}")
                else:
                    accion_unica = data_final.get("accion") or data_final.get("acción")
                    if accion_unica == "FORMULAR_RESPUESTA":
                        respuesta_para_usuario = data_final.get("contenido", "No puedo responder ahora.")
                        self._log_output("response", respuesta_para_usuario)
                        self.conversation_logger.info(f"NeoC: {respuesta_para_usuario.replace('\n', ' ')}")
                        self.memoria_corto_plazo.append(f"NeoC: {respuesta_para_usuario}")

            except (json.JSONDecodeError, AttributeError) as e:
                self.logger.error(f"Error al procesar la respuesta final de EGOS: {e}")
                respuesta_para_usuario = "Hubo un error al formular mi respuesta."
                self._log_output("response", respuesta_para_usuario)
                self.conversation_logger.info(f"NeoC: {respuesta_para_usuario.replace('\n', ' ')}")
                self.memoria_corto_plazo.append(f"NeoC: {respuesta_para_usuario}")
        else:
            self.logger.info("EGOS ha decidido OBSERVAR.")
            self._log_output("log", "EGOS decidió OBSERVAR el estímulo. Sin respuesta verbal.")

        self.logger.info("--- FIN PROCESAMIENTO DE ESTÍMULO ---")