# main.py 1
from src.agent import Agencont
import sys

if __name__ == '__main__':
    agente_neoc = Agencont()
    try:
        agente_neoc.iniciar_bucle_autonomo()
        
        # --- LÍNEAS NUEVAS ---
        # Este código solo se ejecutará si el bucle termina limpiamente (con 'apagar')
        print("\n[NeoC] Bucle finalizado. Sesión terminada.")
        agente_neoc.logger.info("Bucle de pensamiento finalizado de forma controlada.")
        # --- FIN DE LÍNEAS NUEVAS ---

    except KeyboardInterrupt:
        print("\n\n[NeoC] Bucle detenido por el usuario (Ctrl+C). Cerrando sesión.")
        agente_neoc.logger.info("Bucle de pensamiento detenido por el usuario.")
        sys.exit(0)