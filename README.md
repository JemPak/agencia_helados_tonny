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

Abrir <http://localhost:8069> y crear la base de datos con el nombre **`agencia`** (es el que usan los scripts de respaldo):

- País: **Colombia** · Idioma: **Español (CO)**
- Contraseña maestra: la de `admin_passwd` en `config/odoo.conf`

Luego, en **Aplicaciones**, quitar el filtro "Aplicaciones" y buscar e instalar **Agencia de Helados – Base**
(`helados_base`). Instala Inventario como dependencia y deja configuradas las ubicaciones y las categorías.

Al instalarse se carga el **catálogo inicial de la agencia** (16 productos con precio de compra y de venta).
Las imágenes se descargan de heladostonny.com en ese momento; si no hay internet, el módulo se instala
igual y las imágenes se pueden subir a mano.

## Persistencia y respaldos

Los datos **no se pierden al apagar** los contenedores ni al reiniciar el equipo: la base de datos y el
filestore (imágenes y adjuntos) viven en los volúmenes de Docker `agencia_helados_db-data` y
`agencia_helados_odoo-data`, que no dependen de los contenedores.

| Comando | ¿Conserva los datos? |
|---------|----------------------|
| `docker compose stop` / `start` | Sí |
| `docker compose down` / `up -d` | Sí |
| Reiniciar el equipo o Docker | Sí |
| `docker compose down -v` | **No: borra los volúmenes** |
| `docker volume prune` / `docker system prune --volumes` | **No** |

Para tener una copia fuera de Docker (o pasar la base a otro integrante):

```bash
scripts/backup.sh                       # crea backups/agencia-AAAAMMDD-HHMMSS/ (db.dump + filestore.tar.gz)
scripts/restore.sh backups/agencia-...  # reemplaza la base 'agencia' con ese respaldo (pide confirmación)
```

La carpeta `backups/` no se sube al repositorio.

## Módulos propios

### `helados_base` – HU01 Ubicaciones y catálogo de productos

| Criterio de aceptación | Implementación |
|------------------------|----------------|
| Ubicaciones de la agencia | Al instalar, la ubicación de stock del almacén pasa a llamarse **Cava** y se crean **Local** y **Vehículos → Camión, Moto 1, Moto 2**. Se activa "Ubicaciones de almacenamiento". |
| E1 – Registrar producto con stock inicial | *Inventario → Productos → Registrar producto*: código, nombre, categoría, precio de compra, precio de venta y cantidad. Crea el producto, aplica el ajuste de inventario en la Cava y muestra "Producto guardado correctamente". |
| E2 – Validar duplicados, negativos y obligatorios | Código único (sin distinguir mayúsculas/espacios, incluye archivados) también desde el formulario estándar de producto; precio y cantidad contada no negativos; campos obligatorios resaltados en rojo. |
| E3 – Consultar catálogo con saldos | *Inventario → Productos → Catálogo en Cava*: código, nombre, categoría, precios y cantidad **solo en la Cava** (no suma Local ni vehículos). |

Categorías creadas: *Helados Tonny* → Conos, Vasos, Paletas, Galletas, Turrones, Helado por litro.

Catálogo inicial (precios en COP, entregados por la agencia):

| Código | Producto | Categoría | Compra | Venta |
|--------|----------|-----------|-------:|------:|
| LIT-18 | Caja helado 18 L | Helado por litro | 93.979 | 123.585 |
| LIT-10 | Caja helado 10 L | Helado por litro | 55.158 | 72.555 |
| LIT-05 | Caja helado 5 L | Helado por litro | 26.349 | 36.500 |
| CON-BIC | Biconos | Conos | 55.862 | 73.312 |
| CON-KON | Konito | Conos | 45.705 | 59.960 |
| CON-KMA | Konito Maní | Conos | 32.871 | 42.058 |
| VAS-JUN | Vasito Junior | Vasos | 21.056 | 26.250 |
| VAS-DER | Derroche | Vasos | 16.804 | 21.367 |
| VAS-GCI | Gran Circus | Vasos | 2.619 | 3.457 |
| GAL-GAL | Galletas | Galletas | 36.195 | 45.980 |
| PAL-VAL | Vallenitas | Paletas | 50.784 | 64.776 |
| PAL-IRI | Paleta Iris | Paletas | 22.714 | 29.712 |
| PAL-CHO | Chocomanía | Paletas | 42.012 | 53.350 |
| TUR-TUR | Turrones | Turrones | 37.395 | 47.976 |
| TUR-TCI | Turroncitos | Turrones | 36.934 | 47.976 |
| TUR-CRE | Cremosos | Turrones | 18.283 | 23.988 |

Las cantidades iniciales quedan en 0 hasta el primer conteo de la Cava.

## Pruebas

Las pruebas de aceptación corren en una base temporal:

```bash
docker compose run --rm odoo odoo -d pruebas -i helados_base \
  --test-enable --test-tags /helados_base --stop-after-init
docker compose exec db dropdb -U odoo pruebas
```

### Comandos útiles

```bash
docker compose logs -f odoo      # ver logs
docker compose restart odoo      # reiniciar Odoo (p. ej. tras cambiar addons)
docker compose down              # detener (conserva los datos)
docker compose down -v           # ¡detener y BORRAR los datos! (ver Persistencia)
```

## Estructura del repositorio

```
.
├── addons/
│   └── helados_base/       # HU01: ubicaciones y catálogo (models, wizard, views, data, tests)
├── config/
│   └── odoo.conf.example   # plantilla de configuración de Odoo
├── scripts/
│   ├── backup.sh           # respaldo de base + filestore
│   └── restore.sh          # restauración de un respaldo
├── docker-compose.yml
├── .env.example            # plantilla de variables de entorno
└── README.md
```

## Hoja de ruta

- [x] Dockerizar Odoo y PostgreSQL
- [x] Crear la base de datos con localización colombiana
- [x] Persistencia de datos y scripts de respaldo
- [x] HU01 – Ubicaciones y catálogo de productos (`helados_base`)
- [ ] HU02 – Reglas de reabastecimiento y recepciones
- [ ] HU03 – Pedidos a domicilio y cargue de vehículos
- [ ] HU04 – Punto de Venta por vehículo y cierre de sesión
- [ ] HU05 – Reportes para el gerente
- [ ] Guion de pruebas de aceptación
