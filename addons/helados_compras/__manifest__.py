{
    "name": "Agencia de Helados – Compras",
    "summary": "HU02: reabastecimiento automático desde Helados Tonny S.A.S. y recepción en la Cava",
    "version": "19.0.1.1.0",
    "category": "Inventory/Purchase",
    "author": "Equipo Ingeniería de Software UNAL 2026",
    "license": "LGPL-3",
    "depends": ["helados_base", "purchase_stock"],
    "data": [
        "data/res_partner_data.xml",
        "data/reabastecimiento_data.xml",
        "views/stock_picking_views.xml",
        "views/product_views.xml",
    ],
    "application": False,
    "installable": True,
}
