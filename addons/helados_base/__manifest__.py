{
    "name": "Agencia de Helados – Base",
    "summary": "HU01: ubicaciones de inventario (Cava, Local, vehículos) y catálogo de productos",
    "version": "19.0.1.0.0",
    "category": "Inventory/Inventory",
    "author": "Equipo Ingeniería de Software UNAL 2026",
    "license": "LGPL-3",
    "depends": ["stock"],
    "data": [
        "security/ir.model.access.csv",
        "data/stock_location_data.xml",
        "data/product_category_data.xml",
        "wizard/registrar_producto_views.xml",
        "views/product_views.xml",
    ],
    "demo": [
        "demo/product_demo.xml",
    ],
    "application": False,
    "installable": True,
}
