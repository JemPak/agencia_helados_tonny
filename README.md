# Agencia de Helados – Sistema de información en Odoo

Proyecto del curso **Ingeniería de Software** (Universidad Nacional de Colombia – Sede Medellín, 2026).

Implementación de un ERP en **Odoo** para una agencia distribuidora oficial de **Helados Tonny S.A.S.**
en el Suroeste antioqueño. La agencia vende en un local, almacena en una cava refrigerada y distribuye
en ruta con un camión ("punto móvil") y dos motos.

## Problemas que resuelve

| # | Problema actual | Cómo lo resuelve Odoo |
|---|-----------------|-----------------------|
| 1 | Descuadre en el cierre de cuentas del punto móvil: diferencias entre lo vendido, el efectivo recibido y los productos devueltos. | Cada vehículo es una **ubicación de inventario** con su propio **Punto de Venta**. Al cerrar la sesión, Odoo compara el efectivo esperado con el contado y los sobrantes esperados con los devueltos. |
| 2 | Ineficiencia en la gestión de inventario: hay que ir a la bodega y contar a mano para pedir producto nuevo. | Inventario en línea por ubicación y **reglas de stock mínimo/máximo** que generan las solicitudes de compra a Helados Tonny. |

## Alcance (historias de usuario)

| ID | Historia | Rol | Aplicaciones de Odoo |
|----|----------|-----|----------------------|
| HU01 | Configurar ubicaciones y catálogo de productos | Administrador | Inventario |
| HU02 | Reabastecimiento automático y recepción en la Cava | Administrador / Bodeguero | Inventario, Compras |
| HU03 | Pedidos a domicilio y cargue del vehículo | Administrador / Bodeguero | Ventas, Inventario |
| HU04 | Ventas en ruta y cierre de sesión con conciliación | Repartidor | Punto de Venta, Inventario |
| HU05 | Indicadores de ventas, existencias y cierres | Gerente | Ventas, Punto de Venta, Inventario |

El backlog detallado, con los criterios de aceptación, está en el documento del curso.

### Modelo de ubicaciones

```
Almacén
├── Cava (bodega refrigerada)
├── Local (venta al detal)
└── Vehículos
    ├── Camión (punto móvil)
    ├── Moto 1
    └── Moto 2
```

## Arquitectura

```
┌──────────────┐  8069   ┌──────────────┐  5432   ┌──────────────┐
│  Navegador   │ ──────▶ │  odoo:19.0   │ ──────▶ │ postgres:17  │
└──────────────┘         └──────────────┘         └──────────────┘
                           │ /mnt/extra-addons ← ./addons
                           │ /etc/odoo          ← ./config
                           └ volumen odoo-data   (filestore)
                                                    volumen db-data
```

- **odoo**: imagen oficial de Odoo Community.
- **db**: PostgreSQL. Solo es accesible desde la red interna de Docker.
- Los datos viven en volúmenes de Docker, así que sobreviven a `docker compose down`.

## Requisitos

- Docker y Docker Compose v2.
- Puerto 8069 libre (se cambia con `ODOO_PORT` en `.env`).

## Puesta en marcha

```bash
git clone https://github.com/JemPak/agencia_helados_tonny.git
cd agencia_helados_tonny

cp .env.example .env                       # cambiar POSTGRES_PASSWORD
cp config/odoo.conf.example config/odoo.conf  # cambiar admin_passwd

docker compose up -d
```

Abrir <http://localhost:8069> y crear la base de datos:

- País: **Colombia** · Idioma: **Español (CO)**
- Contraseña maestra: la de `admin_passwd` en `config/odoo.conf`

Luego instalar las aplicaciones **Inventario**, **Compras**, **Ventas** y **Punto de Venta**.

### Comandos útiles

```bash
docker compose logs -f odoo      # ver logs
docker compose restart odoo      # reiniciar Odoo (p. ej. tras cambiar addons)
docker compose down              # detener (conserva los datos)
docker compose down -v           # detener y BORRAR los datos
```

## Estructura del repositorio

```
.
├── addons/                 # módulos propios o de terceros (vacío por ahora)
├── config/
│   └── odoo.conf.example   # plantilla de configuración de Odoo
├── docker-compose.yml
├── .env.example            # plantilla de variables de entorno
└── README.md
```

## Hoja de ruta

- [x] Dockerizar Odoo y PostgreSQL
- [ ] Crear la base de datos con localización colombiana
- [ ] HU01 – Ubicaciones y catálogo de productos
- [ ] HU02 – Reglas de reabastecimiento y recepciones
- [ ] HU03 – Pedidos a domicilio y cargue de vehículos
- [ ] HU04 – Punto de Venta por vehículo y cierre de sesión
- [ ] HU05 – Reportes para el gerente
- [ ] Datos de demostración y guion de pruebas de aceptación
