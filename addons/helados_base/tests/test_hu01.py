"""Pruebas de aceptación de la HU01 – Ubicaciones y catálogo de productos."""

from odoo.exceptions import ValidationError
from odoo.tests import Form, TransactionCase, tagged
from odoo.tools.safe_eval import safe_eval


@tagged("post_install", "-at_install", "hu01")
class TestHU01(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Wizard = cls.env["helados.registrar.producto"]
        cls.cava = cls.env.ref("stock.stock_location_stock")
        cls.camion = cls.env.ref("helados_base.location_camion")
        cls.categ_conos = cls.env.ref("helados_base.categoria_conos")

    def _registrar(self, **valores):
        datos = {
            "default_code": "TEST-001",
            "name": "Cono de prueba",
            "categ_id": self.categ_conos.id,
            "list_price": 3500,
            "cantidad_inicial": 50,
        }
        datos.update(valores)
        return self.Wizard.create(datos)._crear_producto()

    # --- Ubicaciones -------------------------------------------------------

    def test_ubicaciones_de_la_agencia(self):
        """Existen Cava, Local, Camión, Moto 1 y Moto 2 dentro del almacén."""
        warehouse = self.env.ref("stock.warehouse0")
        self.assertEqual(self.cava.name, "Cava")
        for xmlid in ("location_local", "location_camion", "location_moto_1", "location_moto_2"):
            ubicacion = self.env.ref(f"helados_base.{xmlid}")
            self.assertEqual(ubicacion.usage, "internal", xmlid)
            self.assertEqual(ubicacion.warehouse_id, warehouse, xmlid)
        self.assertEqual(self.camion.location_id, self.env.ref("helados_base.location_vehiculos"))

    # --- Escenario 1: registrar producto con stock inicial ------------------

    def test_e1_registrar_producto_con_stock_inicial(self):
        template = self._registrar()
        product = template.product_variant_id
        self.assertEqual(product.default_code, "TEST-001")
        self.assertEqual(template.list_price, 3500)
        self.assertTrue(template.is_storable)
        self.assertEqual(product.qty_cava, 50)

    def test_e1_confirmacion_al_guardar(self):
        wizard = self.Wizard.create({
            "default_code": "TEST-002", "name": "Paleta de prueba",
            "categ_id": self.categ_conos.id, "list_price": 2000, "cantidad_inicial": 10,
        })
        accion = wizard.action_registrar()
        self.assertEqual(accion["tag"], "display_notification")
        self.assertEqual(accion["params"]["type"], "success")

    # --- Escenario 2: validaciones -------------------------------------------

    def test_e2_codigo_duplicado(self):
        self._registrar(default_code="TEST-DUP")
        with self.assertRaises(ValidationError):
            self._registrar(default_code=" test-dup ", name="Otro")

    def test_e2_codigo_duplicado_desde_formulario_estandar(self):
        self._registrar(default_code="TEST-DUP2")
        with self.assertRaises(ValidationError):
            self.env["product.product"].create({"name": "Otro", "default_code": "TEST-DUP2"})

    def test_e2_codigo_duplicado_con_archivado(self):
        self._registrar(default_code="TEST-ARCH").active = False
        with self.assertRaises(ValidationError):
            self._registrar(default_code="TEST-ARCH", name="Otro")

    def test_e2_cantidad_negativa(self):
        with self.assertRaises(ValidationError):
            self._registrar(cantidad_inicial=-5)

    def test_e2_precio_negativo(self):
        with self.assertRaises(ValidationError):
            self._registrar(list_price=-1)

    def test_e2_ajuste_inventario_negativo(self):
        product = self._registrar().product_variant_id
        quant = self.env["stock.quant"].search([
            ("product_id", "=", product.id), ("location_id", "=", self.cava.id),
        ])
        with self.assertRaises(ValidationError):
            quant.with_context(inventory_mode=True).inventory_quantity = -3

    def test_e2_campos_obligatorios(self):
        """El formulario no deja guardar si falta código o nombre."""
        form = Form(self.Wizard)
        form.list_price = 1000
        form.cantidad_inicial = 1
        with self.assertRaises(AssertionError):
            form.save()

    # --- Escenario 3: consultar catálogo con saldos en Cava ------------------

    def test_e3_saldo_en_cava_no_incluye_vehiculos(self):
        product = self._registrar(cantidad_inicial=40).product_variant_id
        quant = self.env["stock.quant"].with_context(inventory_mode=True).create({
            "product_id": product.id,
            "location_id": self.camion.id,
            "inventory_quantity": 15,
        })
        quant.action_apply_inventory()
        product.invalidate_recordset(["qty_cava", "qty_available"])
        self.assertEqual(product.qty_cava, 40)
        self.assertEqual(product.qty_available, 55)

    def test_e3_vista_catalogo(self):
        self._registrar()
        accion = self.env.ref("helados_base.action_catalogo_cava")
        productos = self.env["product.product"].search(safe_eval(accion.domain))
        self.assertIn("TEST-001", productos.mapped("default_code"))
