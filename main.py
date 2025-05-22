from flask import Flask, render_template, request, redirect, url_for, jsonify
from flask_mail import Mail, Message
from apscheduler.schedulers.background import BackgroundScheduler
import json
import os
from datetime import datetime, timedelta
from flask import Response

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'bD8k#5gT9r@W2z!E7pVxL3mQ6sA1cY4n')

# Configuración para Flask-Mail
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME', 'edwindjll25@gmail.com')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD', 'powerchu')
app.config['MAIL_DEFAULT_SENDER'] = 'edwindjll25@gmail.com'

mail = Mail(app)

# Base de datos simple en JSON
DB_FILE = 'tasks_db.json'

def load_tasks():
    if not os.path.exists(DB_FILE):
        return {'tasks': [], 'categories': ['Fácil', 'Medio', 'Difícil']}
    
    with open(DB_FILE, 'r') as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {'tasks': [], 'categories': ['Fácil', 'Medio', 'Difícil']}

def save_tasks(data):
    with open(DB_FILE, 'w') as f:
        json.dump(data, f, indent=4)

def send_email_notification(task):
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
        
        msg = Message(subject, recipients=['edwindjll25@gmail.com'])
        msg.body = body
        mail.send(msg)
        return True
    except Exception as e:
        print(f"Error enviando email: {e}")
        return False

def check_due_tasks():
    with app.app_context():
        tasks_data = load_tasks()
        now = datetime.now()
        
        for task in tasks_data['tasks']:
            if not task.get('due_date'):
                continue
                
            due_date = datetime.strptime(task['due_date'], '%Y-%m-%d %H:%M:%S')
            if now >= due_date - timedelta(hours=1) and not task.get('notification_sent', False):
                if send_email_notification(task):
                    task['notification_sent'] = True
                    save_tasks(tasks_data)

# Configurar el scheduler para verificar tareas cada hora
scheduler = BackgroundScheduler()
scheduler.add_job(func=check_due_tasks, trigger="interval", minutes=60)
scheduler.start()

@app.route('/')
def index():
    tasks_data = load_tasks()
    return render_template('index.html', categories=tasks_data['categories'])

@app.route('/add_task', methods=['GET', 'POST'])
def add_task():
    if request.method == 'POST':
        tasks_data = load_tasks()
        
        due_date_str = request.form['due_date']
        due_date = datetime.strptime(due_date_str, '%Y-%m-%dT%H:%M')
        
        new_task = {
            'id': len(tasks_data['tasks']) + 1,
            'title': request.form['title'],
            'description': request.form['description'],
            'category': request.form['category'],
            'priority': request.form['priority'],
            'due_date': due_date.strftime('%Y-%m-%d %H:%M:%S'),
            'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'completed': False,
            'notification_sent': False
        }
        
        tasks_data['tasks'].append(new_task)
        save_tasks(tasks_data)
        
        # Notificar a todos los clientes
        notify_clients('new_task', new_task)
        
        # Enviar email si la tarea es para pronto
        if due_date - datetime.now() <= timedelta(hours=24):
            send_email_notification(new_task)
            new_task['notification_sent'] = True
            save_tasks(tasks_data)
        
        return jsonify({'status': 'success', 'task': new_task})
    
    tasks_data = load_tasks()
    return render_template('add_task.html', categories=tasks_data['categories'])

@app.route('/get_tasks')
def get_tasks():
    tasks_data = load_tasks()
    return jsonify(tasks_data['tasks'])

@app.route('/tasks')
def tasks():
    return render_template('tasks.html')

@app.route('/complete_task/<int:task_id>', methods=['POST'])
def complete_task(task_id):
    tasks_data = load_tasks()
    
    for task in tasks_data['tasks']:
        if task['id'] == task_id:
            task['completed'] = True
            save_tasks(tasks_data)
            notify_clients('task_completed', {'task_id': task_id})
            break
    
    return jsonify({'status': 'success'})

# SSE (Server-Sent Events) para actualizaciones en tiempo real
clients = []

def notify_clients(event_type, data):
    for client in clients:
        try:
            client.queue.put({'type': event_type, 'data': data})
        except:
            clients.remove(client)

class Client:
    def __init__(self):
        self.queue = Queue()

    def generator(self):
        try:
            while True:
                message = self.queue.get()
                yield f"data: {json.dumps(message)}\n\n"
        except GeneratorExit:
            clients.remove(self)

@app.route('/updates')
def updates():
    client = Client()
    clients.append(client)
    return Response(client.generator(), mimetype='text/event-stream')

@app.teardown_appcontext
def shutdown_scheduler(exception=None):
    if scheduler.running:
        scheduler.shutdown()

if __name__ == '__main__':
    from queue import Queue
    app.run(debug=True)
else:
    from queue import Queue