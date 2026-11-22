{
    "name": "Agencia de Helados – Punto de Venta en ruta",
    "summary": "HU04: Punto de Venta por vehículo, base de efectivo, ventas con factura, "
               "devolución de sobrantes y cierre de caja con faltantes",
    "version": "19.0.1.0.0",
    "category": "Sales/Point of Sale",
    "author": "Equipo Ingeniería de Software UNAL 2026",
    "license": "LGPL-3",
    "depends": ["helados_ventas", "pos_sale"],
    "data": [
        "security/ir.model.access.csv",
        "data/pos_data.xml",
        "wizard/devolucion_sobrantes_views.xml",
        "views/helados_faltante_views.xml",
        "views/pos_session_views.xml",
    ],
    "application": False,
    "installable": True,
}
