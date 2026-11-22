{
    "name": "Agencia de Helados – Pedidos y rutas",
    "summary": "HU03: pedidos a domicilio con reserva en la Cava, asignación de repartidor y vehículo, y cargue",
    "version": "19.0.1.0.0",
    "category": "Sales/Sales",
    "author": "Equipo Ingeniería de Software UNAL 2026",
    "license": "LGPL-3",
    "depends": ["helados_base", "sale_stock"],
    "data": [
        "data/stock_warehouse_data.xml",
        "views/sale_order_views.xml",
        "views/stock_picking_views.xml",
    ],
    "application": False,
    "installable": True,
}
