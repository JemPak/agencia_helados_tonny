"""Simula semanas de operación de la agencia sobre una base de Odoo.

DATOS FICTICIOS para demostración: usuarios, clientes y movimientos inventados.
Se ejecuta dentro de `odoo shell` (lo lanza scripts/simular.sh); usa `env`.

Cada día hábil (lunes a sábado), con el reloj de Odoo puesto en esa fecha:
  07:00  se confirman las solicitudes de compra a Tonny y se reciben las órdenes
         confirmadas hace 2 días o más (bodeguero)
  07:30  pedidos a domicilio asignados a cada vehículo; cargue de los pedidos y
         carga extra para venta en ruta; reposición del Local
  08:00  apertura de cajas con base de efectivo
  09-17  ventas: cobro de pedidos a domicilio y ventas sueltas (algunas facturadas)
  18:00  devolución de sobrantes (a veces con faltantes) y cierre de caja (a veces
         con diferencia; si supera el tope, cierra el gerente)
"""

import logging
import os
import random
import uuid
from datetime import datetime, time, timedelta

from freezegun import freeze_time

from odoo import Command, fields
from odoo.exceptions import UserError
from odoo.sql_db import BaseCursor

_logger = logging.getLogger("simulacion")

DIAS = int(os.environ.get("DIAS", "28"))
SEMILLA = int(os.environ.get("SEMILLA", "2026"))
CLAVE_DEMO = "demo2026"
UTC_OFFSET = 5  # Colombia es UTC-5: las 08:00 locales son las 13:00 UTC
BASE_CAJA = 50000

rnd = random.Random(SEMILLA)

# El "ahora" de la base (create_date, fechas de algunos documentos) sigue al reloj congelado
BaseCursor.now = lambda self: fields.Datetime.now()


def a_utc(dia, hora, minuto=0):
    return datetime.combine(dia, time(hora, minuto)) + timedelta(hours=UTC_OFFSET)


# --- Datos maestros ficticios ----------------------------------------------------

MUNICIPIOS = ["Andes", "Jardín", "Betania", "Hispania", "Ciudad Bolívar", "Jericó", "Santa Inés", "Tapartó"]
TIENDAS = [
    "Tienda La Esquina", "Granero El Progreso", "Miscelánea Doña Rosa", "Supermercado El Ahorro",
    "Tienda Los Almendros", "Cafetería El Parque", "Autoservicio La 30", "Tienda El Cafetal",
    "Heladería La Plaza", "Granero San José", "Tienda La Montaña", "Panadería El Trigal",
    "Minimercado Villa Café", "Tienda El Puente", "Estanco La Fonda", "Tienda Mi Pueblo",
]

USUARIOS = [
    # (login, nombre, grupos)
    ("gerente.demo", "Gerente (demo)", [
        "point_of_sale.group_pos_manager", "stock.group_stock_manager",
        "purchase.group_purchase_manager", "sales_team.group_sale_manager",
    ]),
    ("bodeguero.demo", "Bodeguero (demo)", ["stock.group_stock_user", "purchase.group_purchase_user"]),
    ("vendedora.demo", "Vendedora Local (demo)", ["point_of_sale.group_pos_user", "sales_team.group_sale_salesman"]),
    ("repartidor.camion", "Repartidor Camión (demo)", [
        "point_of_sale.group_pos_user", "stock.group_stock_user", "sales_team.group_sale_salesman",
    ]),
    ("repartidor.moto1", "Repartidor Moto 1 (demo)", [
        "point_of_sale.group_pos_user", "stock.group_stock_user", "sales_team.group_sale_salesman",
    ]),
    ("repartidor.moto2", "Repartidor Moto 2 (demo)", [
        "point_of_sale.group_pos_user", "stock.group_stock_user", "sales_team.group_sale_salesman",
    ]),
]


def crear_usuarios():
    usuarios = {}
    for login, nombre, grupos in USUARIOS:
        user = env["res.users"].with_context(active_test=False).search([("login", "=", login)])
        if not user:
            user = env["res.users"].with_context(no_reset_password=True).create({
                "login": login,
                "name": nombre,
                "password": CLAVE_DEMO,
                "tz": "America/Bogota",
                "lang": "es_CO",
                "group_ids": [Command.link(env.ref("base.group_user").id)]
                + [Command.link(env.ref(g).id) for g in grupos],
            })
        usuarios[login] = user
    env.ref("base.user_admin").tz = "America/Bogota"
    return usuarios


def crear_clientes():
    clientes = env["res.partner"]
    for i, nombre in enumerate(TIENDAS):
        partner = env["res.partner"].search([("name", "=", nombre)], limit=1)
        if not partner:
            partner = env["res.partner"].create({
                "name": nombre,
                "is_company": True,
                "city": MUNICIPIOS[i % len(MUNICIPIOS)],
                "country_id": env.ref("base.co").id,
                "customer_rank": 1,
            })
        clientes |= partner
    return clientes


# --- Utilidades de inventario ----------------------------------------------------

def a_mano(product, ubicacion):
    return product.with_context(location=ubicacion.id).qty_available


def libre(product, ubicacion):
    return product.with_context(location=ubicacion.id).free_qty


def ajustar(ubicacion, cantidades):
    for product, qty in cantidades.items():
        quant = env["stock.quant"].with_context(inventory_mode=True).create({
            "product_id": product.id, "location_id": ubicacion.id, "inventory_quantity": qty,
        })
        quant.action_apply_inventory()


def validar(picking, usuario):
    picking = picking.with_user(usuario)
    for move in picking.move_ids:
        move.quantity = move.product_uom_qty
    picking.move_ids.picked = True
    picking.with_context(skip_backorder=True, cancel_backorder=True).button_validate()


def transferir(origen, destino, cantidades, usuario):
    cantidades = {p: q for p, q in cantidades.items() if q > 0}
    if not cantidades:
        return
    warehouse = env.ref("stock.warehouse0")
    picking = env["stock.picking"].create({
        "picking_type_id": warehouse.int_type_id.id,
        "location_id": origen.id,
        "location_dest_id": destino.id,
        "move_ids": [Command.create({
            "product_id": p.id, "product_uom_qty": q, "product_uom": p.uom_id.id,
            "location_id": origen.id, "location_dest_id": destino.id,
        }) for p, q in cantidades.items()],
    })
    picking.action_confirm()
    picking.action_assign()
    validar(picking, usuario)


# --- Compras ------------------------------------------------------------------------

def compras_del_dia(dia, u):
    tonny = env.ref("helados_compras.partner_helados_tonny")
    PO = env["purchase.order"]
    # Solicitudes generadas automáticamente los días anteriores -> el gerente las confirma
    for rfq in PO.search([("partner_id", "=", tonny.id), ("state", "in", ("draft", "sent"))]):
        rfq.with_user(u["gerente.demo"]).button_confirm()
    # Tonny entrega a los 2 días -> el bodeguero recibe
    limite = a_utc(dia, 0) - timedelta(days=1)
    for po in PO.search([("partner_id", "=", tonny.id), ("state", "=", "purchase"), ("date_approve", "<", limite)]):
        for recepcion in po.picking_ids.filtered(lambda p: p.state == "assigned"):
            validar(recepcion, u["bodeguero.demo"])


# --- Pedidos a domicilio y cargue --------------------------------------------------------

def pedidos_y_cargue(dia, u, rutas, clientes, catalogo):
    cava = env.ref("stock.stock_location_stock")
    pedidos = env["sale.order"]
    for ruta in rutas:
        for _ in range(rnd.randint(1, 3)):
            productos = rnd.sample(catalogo, rnd.randint(1, 3))
            lineas = [(p, rnd.randint(1, 4)) for p in productos]
            if any(libre(p, cava) < q for p, q in lineas):
                continue
            pedido = env["sale.order"].with_user(u["gerente.demo"]).create({
                "partner_id": rnd.choice(clientes).id,
                "repartidor_id": ruta["repartidor"].id,
                "vehiculo_id": ruta["ubicacion"].id,
                "order_line": [Command.create({"product_id": p.id, "product_uom_qty": q}) for p, q in lineas],
            })
            try:
                with env.cr.savepoint():
                    pedido.action_confirm()
                    pedidos |= pedido
            except UserError:
                continue
    for pedido in pedidos:
        for cargue in pedido._helados_cargues().filtered(lambda p: p.state == "assigned"):
            validar(cargue, u["bodeguero.demo"])
    # Carga extra para venta en ruta (sin pedido)
    for ruta in rutas:
        extra = {}
        for p in rnd.sample(catalogo, rnd.randint(4, 7)):
            qty = min(rnd.randint(2, 6), int(libre(p, cava)))
            if qty > 0:
                extra[p] = qty
        transferir(cava, ruta["ubicacion"], extra, u["bodeguero.demo"])
    return pedidos


def reponer_local(u, catalogo):
    cava = env.ref("stock.stock_location_stock")
    local = env.ref("helados_base.location_local")
    reposicion = {}
    for p in catalogo:
        falta = 6 - a_mano(p, local)
        if falta > 0:
            reposicion[p] = min(int(falta), int(libre(p, cava)))
    transferir(cava, local, reposicion, u["bodeguero.demo"])


# --- Punto de Venta --------------------------------------------------------------

def abrir(config, usuario):
    config = config.with_user(usuario)
    config.open_ui()
    session = config.current_session_id
    session.set_opening_control(BASE_CAJA, "")
    return session


def vender(session, lineas, cliente=None, facturar=False, pedido=None):
    efectivo = session.config_id.payment_method_ids[:1]
    ui_lines, total = [], 0.0
    for product, qty, so_line in lineas:
        precio = so_line.price_unit if so_line else product.lst_price
        total += precio * qty
        vals = {
            "product_id": product.id, "qty": qty, "price_unit": precio, "discount": 0,
            "price_subtotal": precio * qty, "price_subtotal_incl": precio * qty,
            "tax_ids": [], "pack_lot_ids": [],
        }
        if so_line:
            vals.update(sale_order_line_id=so_line.id, sale_order_origin_id=so_line.order_id.id)
        ui_lines.append(Command.create(vals))
    uid = str(uuid.uuid4())
    # generate_pdf=False: el PDF de la factura se genera al imprimirla, no ahora
    session.env["pos.order"].with_context(generate_pdf=False).sync_from_ui([{
        "uuid": uid, "name": f"Order {uid}",
        "session_id": session.id, "user_id": session.env.uid,
        "date_order": fields.Datetime.to_string(fields.Datetime.now()),
        "partner_id": cliente.id if cliente else False,
        "fiscal_position_id": False, "pricelist_id": session.config_id.pricelist_id.id,
        "lines": ui_lines,
        "payment_ids": [Command.create({
            "amount": total, "name": fields.Datetime.now(), "payment_method_id": efectivo.id,
        })],
        "amount_paid": total, "amount_total": total, "amount_tax": 0, "amount_return": 0,
        "to_invoice": facturar and bool(cliente), "last_order_preparation_change": "{}",
    }])


def ventas_del_dia(dia, session, ubicacion, pedidos, clientes, catalogo, n_sueltas):
    momentos = sorted(a_utc(dia, rnd.randint(9, 16), rnd.randint(0, 59)) for _ in range(len(pedidos) + n_sueltas))
    tareas = [("pedido", p) for p in pedidos] + [("suelta", None)] * n_sueltas
    rnd.shuffle(tareas)
    for momento, (tipo, pedido) in zip(momentos, tareas):
        with freeze_time(momento):
            if tipo == "pedido":
                vender(session, [(l.product_id, l.product_uom_qty, l) for l in pedido.order_line],
                       cliente=pedido.partner_id, facturar=True)
                continue
            disponibles = [p for p in catalogo if libre(p, ubicacion) >= 1]
            if not disponibles:
                continue
            lineas = []
            for p in rnd.sample(disponibles, min(len(disponibles), rnd.randint(1, 3))):
                lineas.append((p, rnd.randint(1, min(3, int(libre(p, ubicacion)))), None))
            cliente = rnd.choice(clientes) if rnd.random() < 0.6 else None
            vender(session, lineas, cliente=cliente, facturar=rnd.random() < 0.35)


def cerrar(session, usuario, gerente):
    session = session.with_user(usuario)
    if session.config_id.es_vehiculo and session.requiere_devolucion:
        wizard = env["helados.devolucion.sobrantes"].with_user(usuario)._crear_para_sesion(session)
        if wizard.linea_ids and rnd.random() < 0.15:  # a veces falta producto
            linea = rnd.choice(wizard.linea_ids)
            linea.devuelto = max(linea.esperado - rnd.randint(1, 2), 0)
        wizard.action_confirmar()

    esperado = session.cash_register_balance_end
    suerte = rnd.random()
    if suerte < 0.75:
        diferencia = 0
    elif suerte < 0.94:
        diferencia = rnd.choice([-1, 1]) * rnd.randrange(500, 4000, 100)
    else:
        diferencia = -rnd.randrange(6000, 20000, 500)
    contado = esperado + diferencia

    try:
        with env.cr.savepoint():
            session.post_closing_cash_details(contado)
            session.update_closing_control_state_session("")
            resultado = session.close_session_from_ui()
            if not resultado.get("successful"):
                raise UserError(resultado.get("message"))
    except UserError:
        # Diferencia sobre el tope: cierra el gerente
        session = session.with_user(gerente)
        session.post_closing_cash_details(contado)
        session.update_closing_control_state_session("Cierre con diferencia autorizado por el gerente")
        session.close_session_from_ui()


# --- Simulación ------------------------------------------------------------------------

def simular():
    hoy = fields.Date.context_today(env["res.users"].browse(env.uid))
    dias = [hoy - timedelta(days=d) for d in range(DIAS, 0, -1)]
    dias = [d for d in dias if d.weekday() != 6]  # sin domingos
    _logger.info("Simulando %s días: %s a %s", len(dias), dias[0], dias[-1])

    categoria = env.ref("helados_base.categoria_helados")
    catalogo = list(env["product.product"].search([("categ_id", "child_of", categoria.id)]))
    cava = env.ref("stock.stock_location_stock")
    local = env.ref("helados_base.location_local")

    with freeze_time(a_utc(dias[0], 6)):
        u = crear_usuarios()
        clientes = list(crear_clientes())
        # Primer conteo de la Cava: cada producto en su máximo
        reglas = env["stock.warehouse.orderpoint"].search([("location_id", "=", cava.id)])
        ajustar(cava, {r.product_id: r.product_max_qty for r in reglas if a_mano(r.product_id, cava) == 0})
        env.cr.commit()

    rutas = [
        {"config": env.ref("helados_pos.pos_config_camion"), "repartidor": u["repartidor.camion"],
         "ubicacion": env.ref("helados_base.location_camion"), "sueltas": (5, 9)},
        {"config": env.ref("helados_pos.pos_config_moto_1"), "repartidor": u["repartidor.moto1"],
         "ubicacion": env.ref("helados_base.location_moto_1"), "sueltas": (3, 6)},
        {"config": env.ref("helados_pos.pos_config_moto_2"), "repartidor": u["repartidor.moto2"],
         "ubicacion": env.ref("helados_base.location_moto_2"), "sueltas": (3, 6)},
    ]
    config_local = env.ref("helados_pos.pos_config_local")

    for dia in dias:
        with freeze_time(a_utc(dia, 7)):
            compras_del_dia(dia, u)
        with freeze_time(a_utc(dia, 7, 30)):
            pedidos = pedidos_y_cargue(dia, u, rutas, clientes, catalogo)
            reponer_local(u, catalogo)
        with freeze_time(a_utc(dia, 8)):
            sesiones = [(r, abrir(r["config"], r["repartidor"])) for r in rutas]
            sesion_local = abrir(config_local, u["vendedora.demo"])
        for ruta, session in sesiones:
            de_la_ruta = pedidos.filtered(lambda p: p.vehiculo_id == ruta["ubicacion"])
            ventas_del_dia(dia, session, ruta["ubicacion"], de_la_ruta, clientes, catalogo,
                           rnd.randint(*ruta["sueltas"]))
        ventas_del_dia(dia, sesion_local, local, env["sale.order"], clientes, catalogo, rnd.randint(6, 12))
        with freeze_time(a_utc(dia, 18)):
            for ruta, session in sesiones:
                cerrar(session, ruta["repartidor"], u["gerente.demo"])
            cerrar(sesion_local, u["vendedora.demo"], u["gerente.demo"])
        env.cr.commit()
        _logger.info("Día %s listo: %s pedidos a domicilio", dia, len(pedidos))

    # Lo que queda pendiente para hoy: solicitudes de compra sin confirmar
    env.cr.commit()
    _logger.info("Simulación terminada")


simular()
