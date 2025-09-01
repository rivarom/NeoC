# src/llm_handler.py

import configparser
import google.generativeai as genai
import os
from dotenv import load_dotenv

# Carga las variables del archivo .env al entorno
load_dotenv()

def llamar_a_gemini(suborgano: str, prompt: str, historial_contexto: list = None):
    """
    Se comunica con la API de Gemini, cargando la API Key de forma segura
    y configurando el modelo, la temperatura y el máximo de tokens de salida
    según el subórgano especificado.
    """
    try:
        # 1. Leer la configuración general desde config.ini
        config = configparser.ConfigParser()
        config.read('config.ini')

        # 2. Cargar la API Key de forma segura desde el archivo .env
        api_key = os.getenv("API_KEY")
        if not api_key:
            raise ValueError("No se encontró la API_KEY en el archivo .env o en las variables de entorno.")

        # 3. Seleccionar dinámicamente los parámetros del subórgano
        model_name = config['MODELS'][f'{suborgano}_MODEL']
        temperature = float(config[f'SETTINGS_{suborgano}']['TEMPERATURE'])
        max_tokens = int(config[f'SETTINGS_{suborgano}']['MAX_OUTPUT_TOKENS'])

        # 4. Configurar la API de Gemini
        genai.configure(api_key=api_key)
        
        generation_config = genai.GenerationConfig(
            temperature=temperature,
            max_output_tokens=max_tokens
        )

        model = genai.GenerativeModel(
            model_name=model_name,
            generation_config=generation_config
        )

        # 5. Enviar el prompt y devolver la respuesta
        chat = model.start_chat(history=historial_contexto if historial_contexto else [])
        response = chat.send_message(prompt)

        return response.text

    except KeyError as e:
        error_message = f"Error de configuración para {suborgano}: no se encontró la clave {e} en config.ini"
        print(error_message)
        return error_message
    except Exception as e:
        error_message = f"Error al llamar a la API de Gemini para {suborgano}: {e}"
        print(error_message)
        return error_message