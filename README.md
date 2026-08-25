# Documentación Técnica y Operativa: CarLogic PWA

## 1. Arquitectura General y Pipeline de Funcionamiento

El sistema se compone de tres capas principales interconectadas de forma automatizada. Al ser una arquitectura Serverless/PaaS, no requiere mantenimiento de servidores.

[ Móvil / PWA ]  <--->  [ Frontend (Vercel) ]
                              │ (HTTPS / REST API)
                              ▼
                        [ Backend (Render / FastAPI) ]
                              │ (Port 6543 / Transaction Pooler IPv4)
                              ▼
                        [ Base de Datos (Supabase / PostgreSQL) ]


### Flujo Operativo Paso a Paso
1. Interfaz (PWA en Vercel): El usuario abre la web app desde la pantalla de inicio de su móvil. La interfaz (HTML/JS estático) renderiza las pestañas de "Planificar" y "Configuración".
2. Petición HTTP (Fetch): Al realizar una acción, JavaScript envía una solicitud REST (GET, POST, DELETE) al backend alojado en Render.
3. Lógica de Negocio (FastAPI): Python procesa la solicitud, calcula los saldos de suma cero y ejecuta las reglas de decisión para seleccionar al conductor.
4. Persistencia (Supabase): El backend se conecta a PostgreSQL a través del Transaction Pooler usando IPv4 (puerto 6543) para consultar o insertar registros.
5. Actualización del DOM: Supabase devuelve la confirmación a Render, Render responde con un JSON a la PWA, y el frontend actualiza la pantalla del usuario.

---

## 2. Lógica del Algoritmo (Suma Cero y Desempates)

El corazón de la API (main.py) se basa en un sistema de Suma Cero para calcular deudas y un sistema de Reglas de Desempate para asignar el coche.

### Sistema de Suma Cero
En cada viaje, el sumatorio de puntos de todos los participantes siempre es 0.
* Fórmula del Pasajero: Puntos = -1 / Número total de personas en el coche
* Fórmula del Conductor: Puntos = (Número total de personas - 1) / Número total de personas
* Ejemplo (4 personas): Cada pasajero recibe -0.25 puntos. El conductor recibe +0.75 puntos. (-0.25 * 3) + 0.75 = 0.

### Algoritmo de Selección de Conductor
Cuando se solicita sugerir un conductor, el sistema filtra a los participantes seleccionados que tienen coche (conduce_habitualmente = true) y aplica estas reglas en orden:
1. Regla 1 (Menor Saldo): Se elige al usuario con el saldo de puntos más bajo (el que más debe).
2. Regla 2 (Menos conducciones): Si hay empate en saldo, se elige al que menos veces haya conducido en el histórico total.
3. Regla 3 (Más tiempo sin conducir): Si persiste el empate, se elige al que haga más tiempo que no conduce.

---

## 3. Inventario de Servicios y Credenciales

| Servicio | Función | URL / Dirección | Configuración Clave |
|---|---|---|---|
| GitHub | Control de código | https://github.com/adriancascudo/CarLogic.git | Rama principal: main |
| Vercel | Hosting Frontend | https://carlogic.vercel.app | Despliegue automático |
| Render | Hosting API | https://carlogic-api.onrender.com | Variable: DATABASE_URL |
| Supabase | Base de Datos | aws-1-eu-west-1.pooler.supabase.com | Puerto 6543 / IPv4 Pooler |

### Cadena de Conexión Exacta (DATABASE_URL)
Esta es la variable de entorno configurada en Render:

postgresql://postgres.nnfgqqzmwzibsjybqytu:4zU*A69.vu)D%3Fjz@aws-1-eu-west-1.pooler.supabase.com:6543/postgres

* Usuario: postgres.nnfgqqzmwzibsjybqytu
* Contraseña original: 4zU*A69.vu)D?jz
* Contraseña codificada: 4zU*A69.vu)D%3Fjz (Obligatorio codificar el símbolo ? como %3F para la URI).

---

## 4. Esquema SQL (Base de Datos)

Este es el script de inicialización ejecutado en Supabase para crear la estructura y las políticas de seguridad (RLS):

CREATE TABLE IF NOT EXISTS usuarios (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    nombre VARCHAR(100) NOT NULL,
    conduce_habitualmente BOOLEAN DEFAULT TRUE,
    creado_en TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS viajes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    fecha DATE NOT NULL,
    conductor_id UUID REFERENCES usuarios(id),
    creado_en TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS viaje_pasajeros (
    viaje_id UUID REFERENCES viajes(id) ON DELETE CASCADE,
    usuario_id UUID REFERENCES usuarios(id),
    PRIMARY KEY (viaje_id, usuario_id)
);

ALTER TABLE usuarios ENABLE ROW LEVEL SECURITY;
ALTER TABLE viajes ENABLE ROW LEVEL SECURITY;
ALTER TABLE viaje_pasajeros ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Permitir todo en usuarios" ON usuarios FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Permitir todo en viajes" ON viajes FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Permitir todo en viaje_pasajeros" ON viaje_pasajeros FOR ALL USING (true) WITH CHECK (true);

---

## 5. Guía de Mantenimiento y Actualizaciones

### Cómo aplicar cambios en el código
Toda actualización se gestiona exclusivamente a través de Git. Los servicios en la nube están escuchando la rama main y se actualizarán de forma automática (CI/CD).

1. Modifica tus archivos locales (index.html para la interfaz, main.py para la lógica).
2. Ejecuta los siguientes comandos en tu terminal:

git add .
git commit -m "feat: descripción de lo que has cambiado"
git push origin main

### Resolución de problemas comunes
* La app móvil no muestra la última actualización: Borra la caché del navegador del teléfono o elimina el icono de la pantalla de inicio y vuelve a instalar la app desde la URL de Vercel.
* Fallo de Base de Datos en Render: Si cambias la contraseña en Supabase, debes recodificar los caracteres especiales a formato URL, ir a Render > Environment, actualizar el valor de DATABASE_URL y guardar para que el servicio se reinicie.
