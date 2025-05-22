// static/script.js
// Configuración de EventSource para actualizaciones en tiempo real
document.addEventListener('DOMContentLoaded', function() {
    // Verificar si estamos en la página de tareas
    if (document.getElementById('tasks-list')) {
        const eventSource = new EventSource('/updates');
        
        eventSource.onmessage = function(event) {
            const data = JSON.parse(event.data);
            console.log('Evento recibido:', data);
            
            if (data.type === 'new_task') {
                showNotification('Nueva tarea agregada: ' + data.data.title, 'success');
                if (typeof updateTaskList === 'function') {
                    updateTaskList();
                }
            } else if (data.type === 'task_completed') {
                showNotification('Tarea completada exitosamente', 'success');
                if (typeof updateTaskList === 'function') {
                    updateTaskList();
                }
            }
        };
        
        eventSource.onerror = function(error) {
            console.error('Error en EventSource:', error);
        };
    }
});

// Función para mostrar notificaciones chingonas
function showNotification(message, type = 'info', duration = 3000) {
    const notification = document.createElement('div');
    notification.className = `notification ${type} notification-bounce`;
    
    // Iconos según el tipo de notificación
    let icon = '';
    switch(type) {
        case 'success':
            icon = '✓';
            break;
        case 'error':
            icon = '✗';
            break;
        case 'warning':
            icon = '⚠';
            break;
        case 'info':
            icon = 'ℹ';
            break;
        default:
            icon = '🔔';
    }
    
    notification.innerHTML = `
        <span style="margin-right: 10px; font-size: 1.2em;">${icon}</span>
        ${message}
    `;
    
    document.body.appendChild(notification);
    
    // Eliminar la notificación después de la duración
    setTimeout(() => {
        notification.classList.add('fade-out');
        setTimeout(() => {
            notification.remove();
        }, 500);
    }, duration);
}

// Función global para actualizar la lista de tareas
window.updateTaskList = function() {
    if (typeof loadTasks === 'function') {
        loadTasks();
    }
};

// Ejemplo de uso:
// showNotification('Tarea agregada con éxito', 'success');
// showNotification('Error al guardar la tarea', 'error');
// showNotification('La tarea está por vencer', 'warning');
// showNotification('Nuevas tareas disponibles', 'info');