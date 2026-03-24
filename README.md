# TechRepair — Sistema de Gestión

Sistema administrativo web para talleres de reparación de equipos electrónicos (celulares, notebooks, PCs y tablets). Permite gestionar clientes, productos, servicios, órdenes de taller, ventas, caja y contabilidad desde una sola interfaz.

---

## Capturas de pantalla

| Nueva Orden de Taller | Crear Cliente desde Taller |
|---|---|
| ![Formulario de taller](https://github.com/user-attachments/assets/a4aa6131-f029-4e28-81a3-01a8584cfd97) | ![Modal nuevo cliente](https://github.com/user-attachments/assets/40db2414-bfc9-45ae-ab73-37e14a659115) |

---

## Funcionalidades

### 👥 Clientes
- Alta, edición y eliminación de clientes
- Búsqueda por nombre, apellido, teléfono o email
- Historial de órdenes de taller y ventas por cliente
- **Creación rápida de clientes directamente desde el formulario de Taller** (sin perder el trabajo en curso)

### 🔧 Taller (Órdenes de Reparación)
- Registro de equipos (tipo, marca, modelo) con descripción del problema
- Estados de la orden: Recibido → En Diagnóstico → En Reparación → Listo → Entregado / Cancelado
- Asignación de técnico y fecha estimada de entrega
- Agregado de productos (piezas) y servicios a cada orden — descuenta stock automáticamente
- Costo calculado automáticamente por piezas + servicios, o ingreso manual del costo final
- Al marcar como **Entregado y Pagado** se registra el ingreso en Caja automáticamente

### 📦 Productos y Servicios
- Gestión de productos con precio de compra/venta, stock actual y stock mínimo
- Gestión de servicios con precio base
- Categorización de productos
- Activar/desactivar productos y servicios

### 📊 Stock
- Vista de productos con alertas de stock bajo
- Ajustes manuales de stock con registro de movimientos
- Historial de movimientos de entrada y salida

### 🛒 Ventas
- Registro de ventas de mostrador (productos y/o servicios)
- Ventas con o sin cliente asignado
- Descuentos por venta
- Integración automática con Caja al registrar una venta

### 💰 Caja
- Registro de ingresos y egresos manuales
- Movimientos generados automáticamente desde Taller y Ventas
- Saldo actual del día y saldo acumulado

### 📈 Contabilidad
- Resumen de ingresos y egresos por período
- Totales de taller, ventas y movimientos manuales

---

## Tecnologías utilizadas

| Componente | Tecnología |
|---|---|
| Backend | Python 3.10+ · Flask 3.0 |
| ORM / Base de datos | Flask-SQLAlchemy 3.1 · PostgreSQL (o SQLite en local) |
| Frontend | Bootstrap 5.3 (local) · Bootstrap Icons 1.11 |
| Templating | Jinja2 |

> Bootstrap y Bootstrap Icons se sirven localmente (carpeta `static/`) — la app funciona sin conexión a internet.

---

## Requisitos

- Python 3.10 o superior
- pip
- PostgreSQL (para producción)

---

## Variables de entorno

| Variable | Descripción | Ejemplo |
|---|---|---|
| `DATABASE_URL` | URI de conexión a la base de datos | `postgresql://user:password@localhost:5432/sistema` |
| `SECRET_KEY` | Clave secreta de Flask | `cambiar-en-produccion` |
| `ARCA_CUIT` | CUIT emisor para factura electrónica | `20123456789` |
| `ARCA_CERT` | Certificado PEM (texto completo) | `-----BEGIN CERTIFICATE-----...` |
| `ARCA_KEY` | Clave privada PEM (texto completo) | `-----BEGIN PRIVATE KEY-----...` |
| `ARCA_CERT_PATH` | Ruta al archivo de certificado (alternativa a `ARCA_CERT`) | `/etc/arca/cert.pem` |
| `ARCA_KEY_PATH` | Ruta al archivo de clave (alternativa a `ARCA_KEY`) | `/etc/arca/key.pem` |
| `ARCA_PROD` | `true` producción, otro valor homologación | `false` |
| `FACTURA_EMISOR_RAZON_SOCIAL` | Razón social para impresión de factura | `URITIC SAS` |
| `FACTURA_EMISOR_DIRECCION` | Domicilio comercial impreso en factura | `Av. Siempre Viva 123` |
| `FACTURA_EMISOR_CONDICION_IVA` | Condición fiscal del emisor en factura | `Responsable Inscripto` |
| `FACTURA_EMISOR_IIBB` | Número de Ingresos Brutos en factura | `901-123456-7` |
| `FACTURA_EMISOR_INICIO_ACTIVIDADES` | Fecha de inicio de actividades en factura | `01/01/2020` |
| `FACTURA_EMISOR_TELEFONO` | Teléfono del emisor en factura | `+54 11 5555-5555` |
| `FACTURA_EMISOR_EMAIL` | Email del emisor en factura | `admin@empresa.com` |

> Si `DATABASE_URL` no está definida, la app usa SQLite (`instance/sistema.db`) como base de datos local.

> Compatibilidad: también se aceptan las variables históricas `AFIP_*`.

### Facturación electrónica ARCA (WSFEv1)

1. Configurá `ARCA_CUIT` y los certificados (`ARCA_CERT` + `ARCA_KEY` o `ARCA_CERT_PATH` + `ARCA_KEY_PATH`).
2. Para pruebas usá homologación (`ARCA_PROD=false`).
3. Para producción usá `ARCA_PROD=true` y certificados válidos en producción.
4. Al registrar una venta con tipo `FACTURA`, el sistema solicita CAE automáticamente y guarda CAE + vencimiento.
5. Desde el detalle de la venta podés usar **Imprimir factura** para generar el comprobante fiscal con datos del emisor/cliente y QR AFIP.

### Preflight ARCA / WSFEv1

Para validar autenticación y conectividad con ARCA sin emitir comprobantes:

```bash
ARCA_CUIT=30718185854 \
ARCA_CERT_PATH="/ruta/al/certificado.crt" \
ARCA_KEY_PATH="/ruta/a/la/clave.key" \
ARCA_PROD=true \
python scripts/arca_preflight.py --tipo-cbte 6 --punto-vta 1
```

Si la configuración es correcta, el script devuelve `AUTH_OK=true` y el último número autorizado para ese tipo de comprobante y punto de venta.

### Emisión mínima controlada

Para previsualizar una factura mínima sin emitirla:

```bash
ARCA_CUIT=30718185854 \
ARCA_CERT_PATH="/ruta/al/certificado.crt" \
ARCA_KEY_PATH="/ruta/a/la/clave.key" \
ARCA_PROD=true \
python scripts/arca_emitir_minima.py --tipo-cbte 6 --punto-vta 1 --importe-total 1.00
```

Para emitir realmente, el script exige confirmación explícita:

```bash
ARCA_CUIT=30718185854 \
ARCA_CERT_PATH="/ruta/al/certificado.crt" \
ARCA_KEY_PATH="/ruta/a/la/clave.key" \
ARCA_PROD=true \
python scripts/arca_emitir_minima.py --tipo-cbte 6 --punto-vta 1 --importe-total 1.00 --emitir --confirmacion EMITIR
```

### Consulta de puntos de venta ARCA

Para listar los puntos de venta que WSFE informa como habilitados:

```bash
ARCA_CUIT=30718185854 \
ARCA_CERT_PATH="/ruta/al/certificado.crt" \
ARCA_KEY_PATH="/ruta/a/la/clave.key" \
ARCA_PROD=true \
python scripts/arca_puntos_venta.py --tipo-cbte 6
```

Para además sondear un rango de puntos de venta con `CompUltimoAutorizado`:

```bash
ARCA_CUIT=30718185854 \
ARCA_CERT_PATH="/ruta/al/certificado.crt" \
ARCA_KEY_PATH="/ruta/a/la/clave.key" \
ARCA_PROD=true \
python scripts/arca_puntos_venta.py --tipo-cbte 6 --scan-desde 1 --scan-hasta 20
```

---

## Instalación y puesta en marcha

### 1. Clonar el repositorio

```bash
git clone https://github.com/gonzalolcortez/Sistema-Backup.git
cd Sistema-Backup
```

### 2. Crear y activar un entorno virtual (recomendado)

```bash
# Mac / Linux
python3 -m venv venv
source venv/bin/activate

# Windows
python -m venv venv
venv\Scripts\activate
```

### 3. Instalar las dependencias

```bash
pip install -r requirements.txt
```

### 4. (Opcional) Cargar datos de demostración

Carga clientes, productos, servicios y órdenes de ejemplo para explorar la app:

```bash
python seed_data.py
```

### 5. Iniciar el servidor

```bash
python app.py
```

Abrí el navegador en **http://localhost:5000**

---

## Estructura del proyecto

```
Sistema-Backup/
├── app.py                  # Aplicación Flask y registro de blueprints
├── extensions.py           # Instancia de SQLAlchemy
├── models.py               # Modelos de base de datos (ORM)
├── seed_data.py            # Script de datos de demostración
├── requirements.txt        # Dependencias Python
│
├── routes/                 # Blueprints por módulo
│   ├── clientes.py         # CRUD clientes + endpoint /nuevo_rapido
│   ├── productos.py        # CRUD productos y servicios
│   ├── stock.py            # Gestión de stock y ajustes
│   ├── taller.py           # Órdenes de reparación
│   ├── ventas.py           # Registro de ventas
│   ├── caja.py             # Movimientos de caja
│   ├── contabilidad.py     # Reportes contables
│   └── dashboard.py        # Página principal / resumen
│
├── templates/              # Plantillas HTML (Jinja2)
│   ├── base.html           # Layout base con sidebar
│   ├── clientes/
│   ├── taller/
│   ├── productos/
│   ├── stock/
│   ├── ventas/
│   ├── caja/
│   └── contabilidad/
│
└── static/                 # Archivos estáticos
    ├── css/
    │   ├── bootstrap.min.css
    │   ├── bootstrap-icons.min.css
    │   └── fonts/
    └── js/
        └── bootstrap.bundle.min.js
```

---

## Base de datos

La app usa **PostgreSQL** en producción. La URI de conexión se configura con la variable de entorno `DATABASE_URL`.

En desarrollo local, si no se define `DATABASE_URL`, se usa SQLite automáticamente (`instance/sistema.db`).

### Configuración con PostgreSQL

1. Crear la base de datos en PostgreSQL:

```sql
CREATE DATABASE sistema;
```

2. Definir la variable de entorno antes de iniciar la app:

```bash
export DATABASE_URL="postgresql://usuario:contraseña@localhost:5432/sistema"
```

3. Las tablas se crean automáticamente al iniciar la app.

### Modelos principales

| Modelo | Descripción |
|---|---|
| `Cliente` | Datos de clientes (nombre, teléfono, email, dirección) |
| `Producto` | Repuestos y accesorios con precio y stock |
| `Servicio` | Servicios de reparación con precio base |
| `Taller` | Órdenes de reparación (asocia cliente, productos y servicios) |
| `Venta` | Ventas de mostrador con sus ítems |
| `MovimientoCaja` | Registro de ingresos y egresos de caja |

---

## Uso rápido

1. **Agregar un cliente**: Menú *Clientes* → *Nuevo Cliente*, o directamente desde el formulario de Taller con el botón 👤+
2. **Registrar una orden de reparación**: Menú *Taller* → *Nueva Orden*
3. **Agregar piezas/servicios a una orden**: Desde el detalle de la orden
4. **Entregar un equipo**: Botón *Entregar y Cobrar* en el detalle de la orden — registra el pago en Caja automáticamente
5. **Registrar una venta**: Menú *Ventas* → *Nueva Venta*
6. **Ver el estado de la caja**: Menú *Caja*

---

## Licencia

Uso privado — todos los derechos reservados.
