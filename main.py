# main.py (modificado)
import tkinter as tk
from tkinter import scrolledtext, Entry, Button
import queue
import threading
from src.agent import Agencont

# --- CLASE PARA LA INTERFAZ GRÁFICA ---
class NeoCGUI:
    def __init__(self, root, input_queue, output_queue):
        self.root = root
        self.input_queue = input_queue
        self.output_queue = output_queue
        
        self.root.title("NeoC Interface")

        # --- Ventana de Pensamiento Interno (Log) ---
        log_frame = tk.Frame(self.root, borderwidth=2, relief="sunken")
        log_frame.pack(padx=10, pady=10, fill="both", expand=True)
        
        log_label = tk.Label(log_frame, text="Flujo de Pensamiento Interno")
        log_label.pack()
        
        self.log_text = scrolledtext.ScrolledText(log_frame, wrap=tk.WORD, state='disabled', height=20)
        self.log_text.pack(padx=5, pady=5, fill="both", expand=True)

        # --- Ventana de Interacción con el Usuario ---
        chat_frame = tk.Frame(self.root, borderwidth=2, relief="sunken")
        chat_frame.pack(padx=10, pady=(0, 10), fill="both", expand=True)

        chat_label = tk.Label(chat_frame, text="Interacción con Usuario")
        chat_label.pack()

        self.chat_text = scrolledtext.ScrolledText(chat_frame, wrap=tk.WORD, state='disabled', height=10)
        self.chat_text.pack(padx=5, pady=5, fill="both", expand=True)

        self.entry_box = Entry(chat_frame, width=80)
        self.entry_box.pack(side="left", padx=5, pady=5, fill="x", expand=True)
        self.entry_box.bind("<Return>", self.send_message)

        send_button = Button(chat_frame, text="Enviar", command=self.send_message)
        send_button.pack(side="right", padx=5, pady=5)

        self.root.after(100, self.process_output_queue)

    def send_message(self, event=None):
        message = self.entry_box.get()
        if message:
            self.input_queue.put(message)
            self.chat_text.config(state='normal')
            self.chat_text.insert(tk.END, f"Usuario: {message}\n")
            self.chat_text.config(state='disabled')
            self.chat_text.see(tk.END) # <-- AÑADIDO: Autoscroll para la ventana de chat
            self.entry_box.delete(0, tk.END)

    def process_output_queue(self):
        try:
            message_data = self.output_queue.get_nowait()
            msg_type = message_data.get("type")
            content = message_data.get("content")

            if msg_type == "log":
                self.log_text.config(state='normal')
                self.log_text.insert(tk.END, f"{content}\n")
                self.log_text.config(state='disabled')
                self.log_text.see(tk.END) # <-- AÑADIDO: Autoscroll para la ventana de logs
            elif msg_type == "response":
                self.chat_text.config(state='normal')
                self.chat_text.insert(tk.END, f"NeoC: {content}\n")
                self.chat_text.config(state='disabled')
                self.chat_text.see(tk.END) # <-- AÑADIDO: Autoscroll para la ventana de chat

                
        except queue.Empty:
            pass
        finally:
            self.root.after(100, self.process_output_queue)

if __name__ == '__main__':
    # 1. Crear las colas de comunicación
    input_q = queue.Queue()
    output_q = queue.Queue()

    # 2. Iniciar el agente en un hilo separado
    agente_neoc = Agencont(input_queue=input_q, output_queue=output_q)
    agent_thread = threading.Thread(target=agente_neoc.iniciar_bucle_autonomo, daemon=True)
    agent_thread.start()

    # 3. Iniciar la GUI en el hilo principal
    root = tk.Tk()
    gui = NeoCGUI(root, input_q, output_q)
    root.mainloop()