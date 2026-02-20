"""Script para cargar datos de demostración."""
from app import app
from extensions import db
from models import (Cliente, Categoria, Producto, Servicio,
                    Taller, TallerProducto, TallerServicio, MovimientoCaja)
from datetime import datetime, timedelta


def seed():
    with app.app_context():
        db.create_all()

        # ── Categorías ────────────────────────────────────────────────────────
        cats = {}
        for nombre in ['Pantallas', 'Baterías', 'Repuestos Varios', 'Accesorios', 'Computadoras', 'Componentes PC']:
            c = Categoria.query.filter_by(nombre=nombre).first()
            if not c:
                c = Categoria(nombre=nombre)
                db.session.add(c)
            cats[nombre] = c
        db.session.flush()

        # ── Productos ─────────────────────────────────────────────────────────
        productos_data = [
            ('Pantalla iPhone 11', 'Pantalla original OEM para iPhone 11', 'Pantallas', 8500, 14000, 6, 3),
            ('Pantalla Samsung A54', 'Display OLED Samsung Galaxy A54', 'Pantallas', 7200, 12500, 4, 3),
            ('Batería iPhone 12', 'Batería Li-Ion 2815mAh compatible', 'Baterías', 2800, 5500, 8, 5),
            ('Batería Samsung A50', 'Batería 4000mAh compatible Samsung', 'Baterías', 1800, 3800, 10, 5),
            ('Conector de carga USB-C', 'Puerto de carga tipo C universal', 'Repuestos Varios', 600, 1500, 15, 5),
            ('Pasta térmica Arctic Silver', 'Pasta conductora de alta calidad', 'Componentes PC', 400, 900, 20, 5),
            ('Memoria RAM DDR4 8GB', 'Módulo RAM DDR4 2666MHz', 'Componentes PC', 9500, 15000, 5, 2),
            ('SSD 240GB Kingston', 'Disco estado sólido SATA III', 'Componentes PC', 11000, 18000, 3, 2),
            ('Funda silicona iPhone 13', 'Funda protectora transparente', 'Accesorios', 300, 800, 25, 10),
            ('Cable USB-C 1m', 'Cable de datos y carga 1 metro', 'Accesorios', 350, 900, 30, 10),
        ]
        prods = {}
        for nombre, desc, cat, pc, pv, stock, minimo in productos_data:
            p = Producto.query.filter_by(nombre=nombre).first()
            if not p:
                p = Producto(nombre=nombre, descripcion=desc,
                             categoria_id=cats[cat].id,
                             precio_compra=pc, precio_venta=pv,
                             stock_actual=stock, stock_minimo=minimo)
                db.session.add(p)
            prods[nombre] = p
        db.session.flush()

        # ── Servicios ─────────────────────────────────────────────────────────
        servicios_data = [
            ('Cambio de pantalla', 'Reemplazo de pantalla con garantía', 3000),
            ('Cambio de batería', 'Reemplazo de batería + calibración', 2000),
            ('Limpieza de liquid damage', 'Limpieza ultrasónica por daño de agua', 4500),
            ('Formateo y reinstalación SO', 'Windows / Android / iOS', 3500),
            ('Diagnóstico', 'Revisión completa del equipo', 1000),
            ('Cambio de teclado notebook', 'Reemplazo de teclado', 5000),
            ('Recuperación de datos', 'Recuperación desde disco dañado', 8000),
        ]
        servs = {}
        for nombre, desc, precio in servicios_data:
            s = Servicio.query.filter_by(nombre=nombre).first()
            if not s:
                s = Servicio(nombre=nombre, descripcion=desc, precio=precio)
                db.session.add(s)
            servs[nombre] = s
        db.session.flush()

        # ── Clientes ──────────────────────────────────────────────────────────
        clientes_data = [
            ('Martín', 'García', '11-4523-8876', 'mgarcia@gmail.com', 'Av. Corrientes 1234, CABA'),
            ('Sofía', 'López', '11-6734-2291', 'sofialopez@hotmail.com', 'Florida 567, CABA'),
            ('Carlos', 'Rodríguez', '11-5542-9900', 'crodriguez@empresa.com', 'Mitre 890, La Plata'),
            ('Ana', 'Martínez', '11-7891-3344', 'anamartinez@gmail.com', 'San Martín 456, Quilmes'),
            ('Juan', 'Fernández', '11-2244-6677', '', 'Belgrano 123, Lanús'),
        ]
        clientes = {}
        for nombre, apellido, tel, email, dir in clientes_data:
            c = Cliente.query.filter_by(nombre=nombre, apellido=apellido).first()
            if not c:
                c = Cliente(nombre=nombre, apellido=apellido, telefono=tel,
                            email=email, direccion=dir)
                db.session.add(c)
            clientes[f'{nombre} {apellido}'] = c
        db.session.flush()

        # ── Órdenes de Taller ─────────────────────────────────────────────────
        from models import Taller as TallerModel
        if TallerModel.query.count() == 0:
            t1 = Taller(
                numero=1,
                cliente_id=clientes['Martín García'].id,
                tipo_equipo='Celular', marca='Apple', modelo='iPhone 11',
                descripcion_problema='Pantalla rota, no responde al tacto',
                estado='en_reparacion',
                costo_estimado=17000.0,
                tecnico='Lucas',
                fecha_ingreso=datetime.utcnow() - timedelta(days=2),
                fecha_estimada_entrega=datetime.utcnow() + timedelta(days=1),
            )
            db.session.add(t1)
            db.session.flush()

            tp1 = TallerProducto(taller_id=t1.id,
                                 producto_id=prods['Pantalla iPhone 11'].id,
                                 cantidad=1, precio_unitario=14000.0)
            ts1 = TallerServicio(taller_id=t1.id,
                                 servicio_id=servs['Cambio de pantalla'].id,
                                 precio=3000.0)
            prods['Pantalla iPhone 11'].stock_actual -= 1
            db.session.add_all([tp1, ts1])

            t2 = Taller(
                numero=2,
                cliente_id=clientes['Sofía López'].id,
                tipo_equipo='Notebook', marca='Lenovo', modelo='IdeaPad 3',
                descripcion_problema='No enciende, posible daño por líquido',
                estado='diagnostico',
                costo_estimado=6000.0,
                tecnico='Lucas',
                fecha_ingreso=datetime.utcnow() - timedelta(days=1),
            )
            db.session.add(t2)
            db.session.flush()

            ts2 = TallerServicio(taller_id=t2.id,
                                 servicio_id=servs['Diagnóstico'].id,
                                 precio=1000.0)
            db.session.add(ts2)

            t3 = Taller(
                numero=3,
                cliente_id=clientes['Carlos Rodríguez'].id,
                tipo_equipo='Celular', marca='Samsung', modelo='Galaxy A54',
                descripcion_problema='Batería se agota rápido, dura menos de 2 horas',
                estado='listo',
                costo_estimado=6000.0,
                costo_reparacion=5800.0,
                tecnico='Marcos',
                fecha_ingreso=datetime.utcnow() - timedelta(days=4),
                fecha_estimada_entrega=datetime.utcnow(),
            )
            db.session.add(t3)
            db.session.flush()

            tp3 = TallerProducto(taller_id=t3.id,
                                 producto_id=prods['Batería Samsung A50'].id,
                                 cantidad=1, precio_unitario=3800.0)
            ts3 = TallerServicio(taller_id=t3.id,
                                 servicio_id=servs['Cambio de batería'].id,
                                 precio=2000.0)
            prods['Batería Samsung A50'].stock_actual -= 1
            db.session.add_all([tp3, ts3])

            # Orden entregada ya pagada
            t4 = Taller(
                numero=4,
                cliente_id=clientes['Ana Martínez'].id,
                tipo_equipo='PC', marca='Genérico', modelo='Desktop',
                descripcion_problema='Lento al iniciar, virus',
                estado='entregado',
                costo_reparacion=3500.0,
                tecnico='Marcos',
                pagado=True,
                fecha_ingreso=datetime.utcnow() - timedelta(days=7),
                fecha_entrega=datetime.utcnow() - timedelta(days=3),
            )
            db.session.add(t4)
            db.session.flush()

            ts4 = TallerServicio(taller_id=t4.id,
                                 servicio_id=servs['Formateo y reinstalación SO'].id,
                                 precio=3500.0)
            db.session.add(ts4)

            # Movimiento de caja para t4
            m4 = MovimientoCaja(
                tipo='ingreso',
                concepto=f'Reparación #4 - Ana Martínez',
                monto=3500.0,
                referencia_tipo='taller',
                referencia_id=t4.id,
                fecha=datetime.utcnow() - timedelta(days=3),
            )
            db.session.add(m4)

        # ── Movimientos extra de caja ─────────────────────────────────────────
        if MovimientoCaja.query.count() < 4:
            extras = [
                ('egreso', 'Compra repuestos proveedor', 12000, timedelta(days=5)),
                ('egreso', 'Alquiler del local', 45000, timedelta(days=10)),
                ('ingreso', 'Venta accesorios mostrador', 4200, timedelta(days=1)),
                ('egreso', 'Servicios luz e internet', 8500, timedelta(days=15)),
                ('ingreso', 'Reparación urgente celular', 7000, timedelta(days=2)),
            ]
            for tipo, concepto, monto, delta in extras:
                mov = MovimientoCaja(
                    tipo=tipo, concepto=concepto, monto=monto,
                    referencia_tipo='otro',
                    fecha=datetime.utcnow() - delta,
                )
                db.session.add(mov)

        db.session.commit()
        print('✅ Datos de demostración cargados correctamente.')
        print(f'   Clientes: {Cliente.query.count()}')
        print(f'   Productos: {Producto.query.count()}')
        print(f'   Servicios: {Servicio.query.count()}')
        print(f'   Órdenes de taller: {TallerModel.query.count()}')
        print(f'   Movimientos de caja: {MovimientoCaja.query.count()}')
        print()
        print('Iniciá el servidor con: python app.py')


if __name__ == '__main__':
    seed()
