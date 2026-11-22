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
Almacén (WH)
├── Cava (bodega refrigerada, stock principal)
├── Local (venta al detal)
└── Salida
    └── Vehículos
        ├── Camión (punto móvil)
        ├── Moto 1
        └── Moto 2
```

Los vehículos están dentro de *Salida* para que Odoo aplique su regla estándar Salida → Cliente
al despachar desde cualquiera de ellos (ver HU03).

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

Luego, en **Aplicaciones**, quitar el filtro "Aplicaciones" y buscar e instalar:

1. **Agencia de Helados – Compras** (`helados_compras`): instala también `helados_base`, Inventario, Compras y
   Contabilidad (con el plan de cuentas colombiano `l10n_co`).
2. **Agencia de Helados – Pedidos y rutas** (`helados_ventas`): instala Ventas.
3. **Agencia de Helados – Punto de Venta en ruta** (`helados_pos`): instala Punto de Venta.

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

## Base de demostración (datos simulados)

Para mostrar el sistema con historia (reportes, cierres, compras) sin ensuciar la base real:

```bash
scripts/simular.sh                          # copia 'agencia' en 'agencia_demo' y simula 28 días
scripts/simular.sh agencia agencia_demo 14  # origen, destino y número de días
```

Todo lo que genera es **ficticio** (`scripts/simulacion/simular_operacion.py`). Por cada día hábil (lunes a
sábado), con el reloj de Odoo puesto en esa fecha:

| Hora | Qué pasa |
|------|----------|
| 07:00 | El gerente confirma las solicitudes de compra automáticas a Tonny; el bodeguero recibe las de hace 2 días. |
| 07:30 | 1 a 3 pedidos a domicilio por vehículo, cargue de pedidos, carga extra para venta en ruta y reposición del Local. |
| 08:00 | Apertura de cajas con base de $50.000. |
| 09:00–17:00 | Cobro de los pedidos a domicilio y ventas sueltas (≈35 % facturadas a tiendas). |
| 18:00 | Devolución de sobrantes (≈15 % con faltantes) y cierre de caja (≈25 % con diferencia; si supera el tope, cierra el gerente). |

El primer día se hace el conteo inicial de la Cava (cada producto en su máximo). La simulación es
reproducible (semilla fija; se cambia con la variable `SEMILLA`).

Usuarios de demostración (clave **`demo2026`**, solo en `agencia_demo`):

| Usuario | Rol |
|---------|-----|
| `gerente.demo` | Gerente: compras, ventas, inventario y Punto de Venta |
| `bodeguero.demo` | Bodeguero: recepciones y cargues |
| `vendedora.demo` | Vendedora del Local |
| `repartidor.camion`, `repartidor.moto1`, `repartidor.moto2` | Repartidores |

Para entrar a la demo, elegir la base `agencia_demo` en <http://localhost:8069/web/database/selector>.

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

### `helados_compras` – HU02 Reabastecimiento y recepciones

| Criterio de aceptación | Implementación |
|------------------------|----------------|
| Configuración | Proveedor **Helados Tonny S.A.S.** registrado en los 16 productos con su precio de compra, y una **regla de stock mínimo/máximo en la Cava** por producto. La ruta Comprar está activa en el almacén. |
| E1 – Solicitud automática por stock mínimo | Cada vez que sale producto de la Cava (venta, entrega o cargue a un vehículo), Odoo revisa de inmediato la regla de ese producto. Si el previsto queda bajo el mínimo, crea o completa la **solicitud de presupuesto** a Tonny por la cantidad que falta para el máximo. Lo ya pedido cuenta, así que no duplica pedidos. El planificador diario de Odoo sigue corriendo como respaldo. |
| E2 – Confirmar orden de compra | *Compras → Solicitudes de presupuesto → Confirmar pedido*: pasa a orden de compra y deja la **recepción pendiente** en la Cava. |
| E3 – Registrar recepción en la Cava | *Inventario → Recepciones → Validar*: suma a la Cava y guarda fecha, proveedor y el nuevo campo **Validado por** (usuario que recibió). Si llega menos de lo pedido, se crea una recepción pendiente por la diferencia. |

**Mínimos y máximos desde la demanda mensual.** Cada producto tiene el campo *Demanda mensual*
(entregado por la agencia). Con la demanda diaria `d = demanda / 30`:

- **Mínimo** = `d × (días de entrega + días de seguridad)` → alcanza mientras llega el pedido.
- **Máximo** = mínimo + `d × días del ciclo de pedido` → lo que se pide cubre hasta el siguiente pedido.

Los días son parámetros del sistema (*Ajustes → Técnico → Parámetros del sistema*). **Los valores por defecto
son supuestos a validar con la agencia**: `helados_compras.dias_entrega = 3`, `dias_seguridad = 2`,
`dias_ciclo = 7`, `dias_mes = 30`. Después de cambiar un parámetro o una demanda, seleccionar los productos y
usar *Acciones → Recalcular mínimos y máximos*.

| Código | Producto | Demanda/mes | Mínimo | Máximo |
|--------|----------|------------:|-------:|-------:|
| LIT-18 | Caja helado 18 L | 120 | 20 | 48 |
| LIT-10 | Caja helado 10 L | 129 | 22 | 52 |
| LIT-05 | Caja helado 5 L | 66 | 11 | 27 |
| CON-BIC | Biconos | 120 | 20 | 48 |
| CON-KON | Konito | 165 | 28 | 66 |
| CON-KMA | Konito Maní | 105 | 18 | 42 |
| VAS-JUN | Vasito Junior | 102 | 17 | 41 |
| VAS-DER | Derroche | 144 | 24 | 58 |
| VAS-GCI | Gran Circus | 180 | 30 | 72 |
| GAL-GAL | Galletas | 105 | 18 | 42 |
| PAL-VAL | Vallenitas | 72 | 12 | 29 |
| PAL-IRI | Paleta Iris | 165 | 28 | 66 |
| PAL-CHO | Chocomanía | 72 | 12 | 29 |
| TUR-TUR | Turrones | 84 | 14 | 34 |
| TUR-TCI | Turroncitos | 84 | 14 | 34 |
| TUR-CRE | Cremosos | 75 | 13 | 30 |

> Mientras la Cava esté en 0, el planificador diario creará una solicitud de compra con todo el catálogo.
> Conviene hacer el primer conteo (ajuste de inventario) antes de empezar a usar Compras.

### `helados_ventas` – HU03 Pedidos a domicilio y traslado a ruta

El pedido a domicilio se despacha en **dos pasos** (entregas en 2 pasos del almacén), así cada unidad
sale de la Cava una sola vez y queda trazada hasta el cliente:

```
Pedido de venta ──confirmar──▶ Cargue de vehículo ──validar──▶ Entrega a domicilio ──validar──▶ Cliente
                               Cava → Camión/Moto              Camión/Moto → Cliente
                               (bodeguero)                     (repartidor, HU04)
```

| Criterio de aceptación | Implementación |
|------------------------|----------------|
| E1 – Crear pedido y reservar en la Cava | Al confirmar el pedido, Odoo **reserva** las unidades en la Cava (siguen ahí, pero ya no están libres) y crea el **cargue**. El pedido tiene los campos **Repartidor**, **Vehículo** y **Municipio de entrega** (ciudad de la dirección de entrega). Repartidor y vehículo se pueden asignar o cambiar hasta que se haga el cargue. |
| E2 – Falta de stock en la Cava | Al digitar una cantidad mayor a la libre en la Cava aparece una **advertencia**. Además, el pedido **no se puede confirmar** si algún producto supera lo libre (cuenta lo ya reservado por otros pedidos y suma líneas repetidas), según la regla de negocio de no vender sin existencias. |
| E3 – Cargue al vehículo | *Inventario → Operaciones → Cargue de vehículos* muestra los cargues listos agrupados por vehículo. Al validarlo, la mercancía sale de la Cava y entra al vehículo, y Odoo crea la **entrega** desde ese vehículo con el mismo repartidor. No se puede validar un cargue sin vehículo ni cambiar el vehículo de un pedido ya cargado. |

Además se activó *Transferencias internas* para cargar mercancía extra a un vehículo (venta en ruta sin
pedido) y, en la HU04, devolver los sobrantes a la Cava.

### `helados_pos` – HU04 Ventas y cierre de sesión en el Punto de Venta

Hay un **Punto de Venta por vehículo** (Camión, Moto 1, Moto 2) y uno para el **Local**. Cada uno vende desde
su propia ubicación, tiene su propia caja de **Efectivo** y un **tope de diferencia al cierre de $5.000**.

```
Abrir caja (base) ─▶ Vender / cobrar pedidos ─▶ Devolver sobrantes ─▶ Contar efectivo y cerrar
                     sale del vehículo            vehículo → Cava       esperado vs. contado
                                                  faltantes registrados
```

| Criterio de aceptación | Implementación |
|------------------------|----------------|
| E1 – Abrir sesión con base de efectivo | El repartidor abre la sesión de su vehículo e ingresa la base; queda como saldo inicial de la caja. |
| E2 – Venta, pago y factura | Cada venta descuenta **en el momento** del inventario del vehículo y registra el pago. Si tiene cliente y se marca *Factura*, genera la factura publicada. Los **pedidos a domicilio** (HU03) se cobran desde el PdV con *Pedidos de venta*: Odoo cancela la entrega pendiente y descuenta una sola vez desde el vehículo. |
| E3 – Devolver sobrantes y cerrar | En la sesión, **Devolver sobrantes** muestra lo que debería quedar en el vehículo (cargado − vendido); el repartidor anota lo que devuelve. Lo devuelto vuelve a la Cava; **lo que falta queda registrado como faltante** (cantidad y valor) a nombre del responsable y el vehículo queda en cero. **No se puede cerrar la caja sin este paso.** Al cerrar, Odoo compara efectivo esperado vs. contado; si la diferencia supera el tope, **solo un gerente** puede cerrar (Odoo lo controlaba solo en pantalla; aquí también en el servidor). |

Los faltantes se consultan en *Punto de Venta → Informes → Faltantes de ruta* (gerente).

Pedidos a domicilio no entregados: al devolver sobrantes se libera su reserva en el vehículo y la entrega
queda pendiente; para volver a salir se carga de nuevo con una transferencia interna Cava → vehículo.

**No implementado (decisión):** Odoo permite vender en el PdV aunque el sistema no tenga existencias en el
vehículo. Bloquearlo exige modificar la pantalla del PdV (JavaScript). Se dejó así porque la devolución de
sobrantes ya detecta cualquier diferencia entre lo cargado y lo vendido.

## Pruebas

Las pruebas de aceptación de todos los módulos corren en una base temporal que se borra al terminar:

```bash
scripts/test.sh                  # todos los módulos de addons/
scripts/test.sh helados_compras  # solo uno
```

El script detiene el Odoo principal mientras corren (sus tareas programadas chocarían con la base de
pruebas) y lo vuelve a iniciar al final. Sale con código 0 si no hay fallos.

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
│   ├── helados_base/       # HU01: ubicaciones y catálogo (models, wizard, views, data, tests)
│   ├── helados_compras/    # HU02: proveedor, reabastecimiento y recepciones
│   ├── helados_ventas/     # HU03: pedidos a domicilio, repartidor/vehículo y cargue
│   └── helados_pos/        # HU04: PdV por vehículo, sobrantes, faltantes y cierre de caja
├── config/
│   └── odoo.conf.example   # plantilla de configuración de Odoo
├── scripts/
│   ├── backup.sh           # respaldo de base + filestore
│   ├── restore.sh          # restauración de un respaldo
│   ├── test.sh             # pruebas de aceptación
│   ├── simular.sh          # base de demostración con operación simulada
│   └── simulacion/         # script de la simulación (datos ficticios)
├── docker-compose.yml
├── .env.example            # plantilla de variables de entorno
└── README.md
```

## Hoja de ruta

- [x] Dockerizar Odoo y PostgreSQL
- [x] Crear la base de datos con localización colombiana
- [x] Persistencia de datos y scripts de respaldo
- [x] HU01 – Ubicaciones y catálogo de productos (`helados_base`)
- [x] HU02 – Reglas de reabastecimiento y recepciones (`helados_compras`)
- [x] HU03 – Pedidos a domicilio y cargue de vehículos (`helados_ventas`)
- [x] HU04 – Punto de Venta por vehículo y cierre de sesión (`helados_pos`)
- [ ] HU05 – Reportes para el gerente
- [ ] Guion de pruebas de aceptación
