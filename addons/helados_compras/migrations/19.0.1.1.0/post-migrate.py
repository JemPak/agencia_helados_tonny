from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """Bases que ya tenían helados_compras 1.0: cargar la demanda mensual y
    recalcular mínimos y máximos de las reglas existentes."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    env["product.template"]._helados_cargar_demanda_inicial()
