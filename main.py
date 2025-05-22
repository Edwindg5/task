from flask import Flask, render_template, request, redirect, url_for, jsonify, Response
from flask_mail import Mail, Message
from apscheduler.schedulers.background import BackgroundScheduler
from queue import Queue
import json
import os
import socket
import smtplib
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

# Inicialización de la aplicación Flask
app = Flask(__name__, static_folder='static', template_folder='templates')
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'bD8k#5gT9r@W2z!E7pVxL3mQ6sA1cY4n')

# Configuración para Vercel
app.config['SERVER_NAME'] = os.environ.get('VERCEL_URL', 'localhost:5000')
if 'VERCEL' in os.environ:
    app.config['PREFERRED_URL_SCHEME'] = 'https'

# Configuración de Flask-Mail con variables de entorno
app.config.update(
    MAIL_SERVER=os.environ.get('MAIL_SERVER', 'smtp.gmail.com'),
    MAIL_PORT=int(os.environ.get('MAIL_PORT', 587)),
    MAIL_USE_TLS=os.environ.get('MAIL_USE_TLS', 'True').lower() == 'true',
    MAIL_USERNAME=os.environ.get('MAIL_USERNAME'),
    MAIL_PASSWORD=os.environ.get('MAIL_PASSWORD'),
    MAIL_DEFAULT_SENDER=os.environ.get('MAIL_DEFAULT_SENDER'),
    MAIL_ASCII_ATTACHMENTS=False,
    MAIL_TIMEOUT=10,
    MAIL_DEBUG=True
)

mail = Mail(app)

# Configuración de la base de datos
DB_FILE = os.environ.get('DB_FILE', 'tasks_db.json')

# Context Processor para inyectar 'now' en todas las plantillas
@app.context_processor
def inject_now():
    return {'now': datetime.now(timezone.utc)}

# Funciones auxiliares
def load_tasks():
    """Carga las tareas desde el archivo JSON."""
    if not os.path.exists(DB_FILE):
        return {'tasks': [], 'categories': ['Fácil', 'Medio', 'Difícil']}
    
    with open(DB_FILE, 'r', encoding='utf-8') as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {'tasks': [], 'categories': ['Fácil', 'Medio', 'Difícil']}

def save_tasks(data):
    """Guarda las tareas en el archivo JSON."""
    with open(DB_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def send_email_notification(task):
    """Envía un correo electrónico de recordatorio."""
    try:
        subject = f"Recordatorio de tarea: {task['title']}"
        body = f"""
        Tarea: {task['title']}
        Categoría: {task['category']}
        Descripción: {task['description']}
        Fecha límite: {task['due_date']}
        Prioridad: {task['priority']}
        
        ¡No olvides completar esta tarea!
        """
        
        msg = Message(
            subject=subject,
            recipients=[os.environ.get('MAIL_RECIPIENT', 'edwindjll25@gmail.com')],
            charset='utf-8'
        )
        msg.body = body
        
        # Configuración manual del timeout
        with app.app_context():
            with mail.connect() as connection:
                if connection:
                    connection.timeout = 10
                    connection.send(msg)
        return True
        
    except smtplib.SMTPException as e:
        print(f"⛔ Error SMTP al enviar email: {str(e)}")
        return False
    except Exception as e:
        print(f"⛔ Error general al enviar email: {str(e)}")
        return False

def check_due_tasks():
    """Verifica tareas próximas a vencer y envía notificaciones."""
    if 'VERCEL' in os.environ:
        return  # Desactivar scheduler en Vercel
        
    with app.app_context():
        tasks_data = load_tasks()
        now = datetime.now(timezone.utc)
        
        for task in tasks_data['tasks']:
            if not task.get('due_date'):
                continue
                
            due_date = datetime.strptime(task['due_date'], '%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc)
            if now >= due_date - timedelta(hours=1) and not task.get('notification_sent', False):
                if send_email_notification(task):
                    task['notification_sent'] = True
                    save_tasks(tasks_data)

# Configuración del scheduler (solo en local)
if 'VERCEL' not in os.environ:
    scheduler = BackgroundScheduler()
    scheduler.add_job(func=check_due_tasks, trigger="interval", minutes=60)
    scheduler.start()

# [Tus rutas existentes permanecen igual...]

# Server-Sent Events (SSE) para actualizaciones en tiempo real
clients = []

def notify_clients(event_type, data):
    """Notifica a los clientes sobre cambios en las tareas."""
    for client in clients:
        try:
            client.queue.put({'type': event_type, 'data': data})
        except:
            clients.remove(client)

class Client:
    """Clase para manejar conexiones SSE."""
    def __init__(self):
        self.queue = Queue()

    def generator(self):
        """Genera eventos para el cliente."""
        try:
            while True:
                message = self.queue.get()
                yield f"data: {json.dumps(message)}\n\n"
        except GeneratorExit:
            clients.remove(self)

@app.route('/updates')
def updates():
    """Endpoint para actualizaciones en tiempo real."""
    client = Client()
    clients.append(client)
    return Response(client.generator(), mimetype='text/event-stream')

@app.teardown_appcontext
def shutdown_scheduler(exception=None):
    """Apaga el scheduler al cerrar la aplicación."""
    if 'scheduler' in globals() and scheduler.running:
        scheduler.shutdown()

# Configuración para Vercel
def create_app():
    return app

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
else:
    application = create_app()